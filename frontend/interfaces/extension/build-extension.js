#!/usr/bin/env node

import fs from "fs";
import path from "path";
import { config } from "dotenv";

// Load environment variables from root .env file
config({ path: "../../../.env" });

console.log("🔧 Building ORII Chrome Extension...");

// Read the built index.html and convert it to sidebar.html
const distIndexPath = "dist/index.html";
const sidebarHtmlPath = "sidebar.html";

if (fs.existsSync(distIndexPath)) {
  let indexContent = fs.readFileSync(distIndexPath, "utf8");

  // Update paths to be relative to the extension root
  indexContent = indexContent.replace(/src="\.\/js\//g, 'src="./dist/js/');
  indexContent = indexContent.replace(/href="\.\/css\//g, 'href="./dist/css/');
  indexContent = indexContent.replace(
    /src="\.\/assets\//g,
    'src="./dist/assets/'
  );

  fs.writeFileSync(sidebarHtmlPath, indexContent);
  console.log("✅ Generated sidebar.html from built React app");
} else {
  console.error("❌ Could not find dist/index.html - build may have failed");
  process.exit(1);
}

// Generate manifest.json from template with environment variables
const manifestTemplatePath = "manifest.template.json";
const manifestPath = "manifest.json";

if (fs.existsSync(manifestTemplatePath)) {
  let manifestContent = fs.readFileSync(manifestTemplatePath, "utf8");

  // Replace placeholders with environment variables
  const googleClientId = process.env.GOOGLE_CLIENT_ID;
  if (googleClientId) {
    manifestContent = manifestContent.replace(
      "{{GOOGLE_CLIENT_ID}}",
      googleClientId
    );
    fs.writeFileSync(manifestPath, manifestContent);
    console.log(
      "✅ Generated manifest.json from template with Google Client ID"
    );
  } else {
    console.warn("⚠️  GOOGLE_CLIENT_ID not found in environment variables");
    console.warn("🔧 Using template as-is - OAuth may not work");
    fs.writeFileSync(manifestPath, manifestContent);
  }
} else {
  console.error("❌ Could not find manifest.template.json");
}

console.log("✅ Extension build completed!");
console.log("📁 Files generated:");
console.log("  - sidebar.html (React-powered)");
console.log("  - dist/ folder with compiled React app");
console.log("🚀 Extension is ready for Chrome installation!");
