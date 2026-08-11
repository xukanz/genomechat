# R Code Execution Rules

You are writing R code that runs in an isolated sandbox with `execute_r_code`.

## S3 Helper Usage

The sandbox has `r_helpers.R` pre-installed. Source it at the top of every script:

```r
source("r_helpers.R")
```

**API Reference:**
```r
source("r_helpers.R")

# Reading data
df <- read_csv_from_s3(key)                         # -> data.frame
df <- read_csv_from_s3(key, bucket = "my-bucket")   # explicit bucket
text <- read_file_from_s3(key)                       # -> character

# Writing/uploading
upload_file_to_s3(local_path, key)                   # upload local file
write_csv_to_s3(df, key)                             # write data.frame as CSV

# Save + track in one call (PREFERRED)
save_and_track(local_path, s3_key)                   # upload AND track for s3_results.json

# Write s3_results.json at end of script
write_s3_results()                                   # MUST call at end if using track functions
```

**WARNING**: The signature is `(key, bucket)` NOT `(bucket, key)`. Bucket is optional.

## Plot Saving Rules

1. **ALWAYS use `ggsave()`** for ggplot2 plots
2. **NEVER use `png()/dev.off()`** for ggplot -- use `ggsave()` instead
3. **NEVER use `install.packages()`** -- all packages are pre-installed
4. **Use `suppressPackageStartupMessages(library(...))`** to reduce noise

## Directory Creation

```r
dir.create("outputs/plots", recursive = TRUE, showWarnings = FALSE)
dir.create("outputs/data", recursive = TRUE, showWarnings = FALSE)
```

## Plot + S3 Upload Pattern (CORRECT)

```r
source("r_helpers.R")
suppressPackageStartupMessages(library(ggplot2))

USER_ID <- "<<USER_ID>>"
default_bucket <- Sys.getenv("AWS_DEFAULT_BUCKET", "")
timestamp <- format(Sys.time(), "%Y-%m-%d_%H-%M-%S")

dir.create("outputs/plots", recursive = TRUE, showWarnings = FALSE)

# Create plot
p <- ggplot(mtcars, aes(x = wt, y = mpg)) +
    geom_point() +
    labs(title = "Weight vs MPG", x = "Weight (1000 lbs)", y = "Miles per Gallon") +
    theme_minimal()

# Save locally
filename <- sprintf("outputs/plots/weight_vs_mpg_%s.png", timestamp)
ggsave(filename, plot = p, width = 10, height = 6, dpi = 300)

# Upload to S3 and track
if (nchar(default_bucket) > 0) {
    s3_key <- sprintf("users/%s/visualizations/%s", USER_ID, basename(filename))
    tryCatch({
        save_and_track(filename, s3_key)
    }, error = function(e) {
        cat(sprintf("S3 upload failed: %s\n", e$message))
    })
}

# Write s3_results.json
write_s3_results()
```

## Multiple Plots Pattern

```r
source("r_helpers.R")
suppressPackageStartupMessages(library(ggplot2))

USER_ID <- "<<USER_ID>>"
default_bucket <- Sys.getenv("AWS_DEFAULT_BUCKET", "")
timestamp <- format(Sys.time(), "%Y-%m-%d_%H-%M-%S")

dir.create("outputs/plots", recursive = TRUE, showWarnings = FALSE)

# Plot 1
p1 <- ggplot(mtcars, aes(x = factor(cyl), y = mpg)) +
    geom_boxplot() +
    labs(title = "MPG by Cylinder Count") +
    theme_minimal()
f1 <- sprintf("outputs/plots/mpg_by_cyl_%s.png", timestamp)
ggsave(f1, plot = p1, width = 10, height = 6, dpi = 300)

# Plot 2
p2 <- ggplot(mtcars, aes(x = hp, y = mpg, color = factor(cyl))) +
    geom_point(size = 3) +
    labs(title = "HP vs MPG") +
    theme_minimal()
f2 <- sprintf("outputs/plots/hp_vs_mpg_%s.png", timestamp)
ggsave(f2, plot = p2, width = 10, height = 6, dpi = 300)

# Upload all to S3
if (nchar(default_bucket) > 0) {
    for (f in c(f1, f2)) {
        s3_key <- sprintf("users/%s/visualizations/%s", USER_ID, basename(f))
        tryCatch(save_and_track(f, s3_key), error = function(e) {
            cat(sprintf("Upload failed for %s: %s\n", f, e$message))
        })
    }
}

write_s3_results()
```

## Large Data File Pattern

```r
source("r_helpers.R")

USER_ID <- "<<USER_ID>>"
default_bucket <- Sys.getenv("AWS_DEFAULT_BUCKET", "")
timestamp <- format(Sys.time(), "%Y-%m-%d_%H-%M-%S")

dir.create("outputs", recursive = TRUE, showWarnings = FALSE)

# Process data
results <- data.frame(group = c("A", "B"), mean_value = c(1.5, 2.3))
local_file <- sprintf("outputs/analysis_results_%s.csv", timestamp)
write.csv(results, local_file, row.names = FALSE)

# Upload to S3
if (nchar(default_bucket) > 0) {
    s3_key <- sprintf("users/%s/analysis/%s", USER_ID, basename(local_file))
    save_and_track(local_file, s3_key)
}

write_s3_results()
```

## Code Style Standards

- Use tidyverse conventions: pipe operator (`%>%` or `|>`), dplyr verbs
- Use `<-` for assignment (not `=`)
- Use meaningful variable names (e.g., `patient_data` not `df1`)
- Use `cat()` or `print()` to display results
- Use `suppressPackageStartupMessages()` for library imports

## Visualization Style

- Use `theme_minimal()` or `theme_bw()` as default ggplot theme
- Colorblind-friendly palettes: `scale_fill_viridis_d()`, `scale_color_brewer(palette = "Set2")`
- `ggsave()` with `width = 10, height = 6, dpi = 300` for single plots
- `ggsave()` with `width = 14, height = 10, dpi = 300` for multi-panel
- Use `patchwork` or `cowplot` for combining plots if available

## Available R Packages

**Core:**
- `tidyverse` (dplyr, tidyr, readr, stringr, purrr, forcats, tibble, ggplot2)
- `data.table` - fast data manipulation
- `jsonlite` - JSON parsing
- `httr` - HTTP requests

**Visualization:**
- `ggplot2` - grammar of graphics
- `plotly` - interactive plots
- `circlize` - circular visualizations (chord diagrams)

**Statistics & Survival:**
- `survival` - survival analysis (Surv, survfit, coxph)
- `survminer` - survival plot helpers (ggsurvplot)

**Bioinformatics:**
- `qqman` - Manhattan and Q-Q plots for GWAS results

**S3 Access:**
- `aws.s3` - AWS S3 operations (used internally by r_helpers.R)

## Loading Data with s3_inputs

```r
# In execute_r_code tool call, pass s3_inputs parameter:
# s3_inputs = [{"bucket": "my-bucket", "key": "path/to/data.csv", "local_path": "data.csv"}]
#
# Then in your R code:
df <- read.csv("data.csv", stringsAsFactors = FALSE)
cat(sprintf("Loaded %d rows\n", nrow(df)))
```

## Base R Plot Alternative (for non-ggplot)

When using base R plotting (not ggplot2), use `png()/dev.off()`:

```r
png("outputs/plots/base_plot.png", width = 10, height = 6, units = "in", res = 300)
plot(x, y, main = "Title", xlab = "X", ylab = "Y")
dev.off()
```
