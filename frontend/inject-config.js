#!/usr/bin/env node
/**
 * Runtime configuration injection script.
 *
 * This script injects the API URL into the built HTML file at container startup.
 * It supports two modes:
 *
 * 1. Environment Variable Mode (default):
 *    - Reads VITE_API_URL from environment variables
 *    - Set via container environment variables
 *
 * 2. Vault Secrets Mode (when USE_VAULT_SECRETS=true):
 *    - Reads from /secrets/secret.yaml
 *    - Mounted by Vault Secrets
 */

const fs = require('fs');
const path = require('path');

const USE_VAULT_SECRETS = process.env.USE_VAULT_SECRETS === 'true';
const SECRETS_PATH = '/secrets/secret.yaml';
const HTML_PATH = '/usr/share/nginx/html/index.html';
const CONFIG_SCRIPT_ID = 'runtime-config';

// Get API URL from environment variable first
let apiUrl = process.env.VITE_API_URL || process.env.API_URL;

// If using vault secrets, try to read from there
if (USE_VAULT_SECRETS && fs.existsSync(SECRETS_PATH)) {
  try {
    const yamlContent = fs.readFileSync(SECRETS_PATH, 'utf-8');
    const lines = yamlContent.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;

      const match = trimmed.match(/^([^:]+):\s*(.+)$/);
      if (match) {
        const key = match[1].trim();
        let value = match[2].trim();

        // Remove quotes if present
        if ((value.startsWith('"') && value.endsWith('"')) ||
            (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }

        if (key === 'VITE_API_URL' || key === 'API_URL') {
          apiUrl = value;
          console.log(`Found API URL in vault secrets: ${apiUrl}`);
          break;
        }
      }
    }
  } catch (error) {
    console.warn(`Error reading vault secrets: ${error.message}`);
  }
}

// If no API URL found, skip injection
if (!apiUrl) {
  console.log('No VITE_API_URL or API_URL found. Using build-time config.');
  process.exit(0);
}

// Check if HTML file exists
if (!fs.existsSync(HTML_PATH)) {
  console.warn(`HTML file not found at ${HTML_PATH}. Skipping injection.`);
  process.exit(0);
}

try {
  // Read HTML file
  let htmlContent = fs.readFileSync(HTML_PATH, 'utf-8');

  // Remove existing config script if present
  htmlContent = htmlContent.replace(
    new RegExp(`<script[^>]*id="${CONFIG_SCRIPT_ID}"[^>]*>.*?</script>`, 's'),
    ''
  );
  // Also remove old vault-secrets-config script if present
  htmlContent = htmlContent.replace(
    new RegExp(`<script[^>]*id="vault-secrets-config"[^>]*>.*?</script>`, 's'),
    ''
  );

  // Create config script tag
  const configScript = `\n    <script id="${CONFIG_SCRIPT_ID}">window.__API_URL__ = ${JSON.stringify(apiUrl)};</script>`;

  // Inject before </head>
  if (htmlContent.includes('</head>')) {
    htmlContent = htmlContent.replace('</head>', `${configScript}\n  </head>`);
  } else if (htmlContent.includes('</body>')) {
    htmlContent = htmlContent.replace('</body>', `${configScript}\n  </body>`);
  } else {
    htmlContent = configScript + '\n' + htmlContent;
  }

  // Write modified HTML
  fs.writeFileSync(HTML_PATH, htmlContent, 'utf-8');

  console.log(`Successfully injected API URL: ${apiUrl}`);
} catch (error) {
  console.error(`Error injecting config: ${error.message}`);
  console.error('Falling back to build-time configuration');
  process.exit(0);
}
