# Python Code Execution Rules

You are writing Python code that runs in an isolated sandbox with `execute_code`.

## S3 Helper Usage

The sandbox has `s3_helpers` module pre-installed. Import it at the top of every script:

```python
from s3_helpers import upload_file_to_s3, read_csv_from_s3, read_file_from_s3
```

**API Reference:**
```python
from s3_helpers import read_csv_from_s3, read_file_from_s3, upload_file_to_s3, write_csv_to_s3

# Reading data
df = read_csv_from_s3(key)                        # -> pd.DataFrame
df = read_csv_from_s3(key, bucket="my-bucket")     # explicit bucket
text = read_file_from_s3(key)                      # -> str

# Writing/uploading
upload_file_to_s3(local_path, key)                 # upload local file
write_csv_to_s3(df, key)                           # write DataFrame as CSV
```

**WARNING**: The signature is `(key, bucket)` NOT `(bucket, key)`. Bucket is optional.

## Plot Saving Rules

1. **NEVER use `plt.show()`** - The environment does NOT support interactive plots
2. **ALWAYS use `plt.savefig()`** to save plots as PNG files locally first
3. **Required Pattern**: `plt.savefig('outputs/plots/descriptive_name_YYYY-MM-DD_HH-MM-SS.png')`
4. **ALWAYS call `plt.close()` or `plt.clf()` after saving** to free memory
5. **Use `MPLBACKEND=Agg`** (already set in environment)

## Directory Creation

```python
import os
os.makedirs('outputs/plots', exist_ok=True)
os.makedirs('outputs/data', exist_ok=True)
```

## Plot + S3 Upload Pattern (CORRECT)

```python
import matplotlib.pyplot as plt
from datetime import datetime
from s3_helpers import upload_file_to_s3
import os
import json

USER_ID = "<<USER_ID>>"
s3_files_created = []
default_bucket = os.getenv('AWS_DEFAULT_BUCKET')
timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

os.makedirs('outputs/plots', exist_ok=True)

# Create plot
plt.figure(figsize=(10, 6))
plt.bar(categories, values)
plt.title('My Plot Title')

# Save locally
filename = f'outputs/plots/plot_description_{timestamp}.png'
plt.savefig(filename, dpi=300, bbox_inches='tight')
plt.close()

# Upload to S3
if default_bucket:
    s3_key = f'users/{USER_ID}/visualizations/{os.path.basename(filename)}'
    try:
        upload_file_to_s3(filename, s3_key)
        s3_files_created.append({"bucket": default_bucket, "key": s3_key})
    except Exception as e:
        print(f"S3 upload failed: {type(e).__name__}: {str(e)}")

# Report all files
if s3_files_created:
    with open('s3_results.json', 'w') as f:
        json.dump({"created": s3_files_created}, f)
```

## Large Data File Pattern

```python
import pandas as pd
from s3_helpers import upload_file_to_s3
import os, json
from datetime import datetime

USER_ID = "<<USER_ID>>"
os.makedirs('outputs', exist_ok=True)

df = pd.DataFrame(...)
timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
local_file = f'outputs/analysis_results_{timestamp}.csv'
df.to_csv(local_file, index=False)

default_bucket = os.getenv('AWS_DEFAULT_BUCKET')
if default_bucket:
    s3_key = f'users/{USER_ID}/analysis/{os.path.basename(local_file)}'
    upload_file_to_s3(local_file, s3_key)
    with open('s3_results.json', 'w') as f:
        json.dump({"created": [{"bucket": default_bucket, "key": s3_key}]}, f)
```

## Code Style Standards

- **PEP 8 Compliance**: 4 spaces, max 88 chars, snake_case
- **Imports**: stdlib first, third-party second, local last
- Use meaningful variable names (e.g., `patient_data` not `df1`)
- Use `print(...)` to display results or debug values
- Use vectorized pandas/numpy operations instead of loops

## Visualization Style

- `sns.set_style("whitegrid")` or `sns.set_theme()`
- Colorblind-friendly palettes: `sns.color_palette("colorblind")` or `tab10`
- `bbox_inches='tight'` to avoid clipping
- `plt.tight_layout(pad=2.0)` for multi-panel figures

## Available Python Packages

- `pandas` - data manipulation and analysis
- `numpy` - numerical operations
- `matplotlib` - data visualization
- `seaborn` - statistical visualization
- `scipy` - statistical tests, scientific computing
- `statsmodels` - statistical modeling (OLS, GLM, time series)
- `plotly` - interactive visualizations
- `openpyxl` - Excel file handling
- `pillow` - image processing
- `boto3` - S3 operations (via s3_helpers module)
- `lifelines` - survival analysis

## Loading Data with s3_inputs

```python
# In execute_code tool call, pass s3_inputs parameter:
# s3_inputs = [{"bucket": "my-bucket", "key": "path/to/data.csv", "local_path": "data.csv"}]
#
# Then in your code:
import pandas as pd
df = pd.read_csv("data.csv")  # File downloaded directly to sandbox
```
