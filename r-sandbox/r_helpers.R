# S3 helper functions for R sandbox code execution.
#
# This module provides convenient functions for reading and writing files to/from AWS S3.
# It is automatically copied into each job directory, making it sourceable by executed code.
#
# Usage: source("r_helpers.R") at the top of your R script.

suppressPackageStartupMessages(library(aws.s3))
suppressPackageStartupMessages(library(jsonlite))

# Internal: S3 file tracker (accumulates files created during execution)
.s3_tracker <- new.env(parent = emptyenv())
.s3_tracker$files <- list()


get_default_bucket <- function() {
    bucket <- Sys.getenv("AWS_DEFAULT_BUCKET", "")
    if (nchar(bucket) == 0) return(NULL)
    return(bucket)
}


get_s3_client_args <- function(bucket) {
    # Returns a list of common S3 arguments for aws.s3 functions
    list(
        region = Sys.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        key = Sys.getenv("AWS_ACCESS_KEY_ID", ""),
        secret = Sys.getenv("AWS_SECRET_ACCESS_KEY", ""),
        session_token = Sys.getenv("AWS_SESSION_TOKEN", "")
    )
}


resolve_bucket <- function(bucket = NULL) {
    if (is.null(bucket)) {
        bucket <- get_default_bucket()
        if (is.null(bucket)) {
            stop("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
        }
    }
    return(bucket)
}


read_csv_from_s3 <- function(key, bucket = NULL) {
    bucket <- resolve_bucket(bucket)
    args <- get_s3_client_args(bucket)

    cat(sprintf("[S3] Reading CSV: s3://%s/%s\n", bucket, key))
    obj <- aws.s3::get_object(
        object = key, bucket = bucket,
        region = args$region, key = args$key,
        secret = args$secret, session_token = args$session_token
    )
    df <- read.csv(text = rawToChar(obj), stringsAsFactors = FALSE)
    cat(sprintf("[S3] Read %d rows, %d columns\n", nrow(df), ncol(df)))
    return(df)
}


read_file_from_s3 <- function(key, bucket = NULL) {
    bucket <- resolve_bucket(bucket)
    args <- get_s3_client_args(bucket)

    cat(sprintf("[S3] Reading file: s3://%s/%s\n", bucket, key))
    obj <- aws.s3::get_object(
        object = key, bucket = bucket,
        region = args$region, key = args$key,
        secret = args$secret, session_token = args$session_token
    )
    return(rawToChar(obj))
}


write_csv_to_s3 <- function(df, key, bucket = NULL) {
    bucket <- resolve_bucket(bucket)
    args <- get_s3_client_args(bucket)

    tmp <- tempfile(fileext = ".csv")
    write.csv(df, tmp, row.names = FALSE)

    cat(sprintf("[S3] Writing CSV: s3://%s/%s\n", bucket, key))
    aws.s3::put_object(
        file = tmp, object = key, bucket = bucket,
        region = args$region, key = args$key,
        secret = args$secret, session_token = args$session_token
    )
    cat(sprintf("[S3] CSV uploaded: s3://%s/%s\n", bucket, key))
    unlink(tmp)
}


upload_file_to_s3 <- function(local_path, key, bucket = NULL) {
    bucket <- resolve_bucket(bucket)
    args <- get_s3_client_args(bucket)

    file_size <- file.info(local_path)$size
    cat(sprintf("[S3] Uploading %s (%d bytes)\n", local_path, file_size))

    aws.s3::put_object(
        file = local_path, object = key, bucket = bucket,
        region = args$region, key = args$key,
        secret = args$secret, session_token = args$session_token
    )
    cat(sprintf("[S3] Upload successful: s3://%s/%s\n", bucket, key))
}


list_s3_files <- function(prefix = "", bucket = NULL) {
    bucket <- resolve_bucket(bucket)
    args <- get_s3_client_args(bucket)

    result <- aws.s3::get_bucket(
        bucket = bucket, prefix = prefix,
        region = args$region, key = args$key,
        secret = args$secret, session_token = args$session_token
    )
    keys <- sapply(result, function(x) x$Key)
    return(keys)
}


track_s3_file <- function(key, bucket = NULL) {
    # Track an S3 file for reporting in s3_results.json
    bucket <- resolve_bucket(bucket)
    .s3_tracker$files <- c(
        .s3_tracker$files,
        list(list(bucket = bucket, key = key))
    )
}


save_and_track <- function(local_path, s3_key, bucket = NULL) {
    # Upload a local file to S3 and track it for s3_results.json reporting.
    # This is the preferred single-call function for saving + tracking.
    bucket <- resolve_bucket(bucket)
    upload_file_to_s3(local_path, s3_key, bucket)
    track_s3_file(s3_key, bucket)
}


write_s3_results <- function() {
    # Write s3_results.json with all tracked S3 files.
    # Call this at the END of your script to report all created files.
    if (length(.s3_tracker$files) > 0) {
        results <- list(created = .s3_tracker$files)
        writeLines(toJSON(results, auto_unbox = TRUE), "s3_results.json")
        cat(sprintf("[S3] Wrote s3_results.json with %d file(s)\n",
                    length(.s3_tracker$files)))
    }
}
