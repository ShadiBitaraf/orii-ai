#!/usr/bin/env node

import fs from "fs";
import path from "path";

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

console.log("✅ Extension build completed!");
console.log("📁 Files generated:");
console.log("  - sidebar.html (React-powered)");
console.log("  - dist/ folder with compiled React app");
console.log("🚀 Extension is ready for Chrome installation!");
