// ORII Calendar Assistant - Content Script
console.log(
  "🎯 ORII CONTENT SCRIPT LOADED! This should appear in console immediately."
);

// Global variables
let sidebarContainer = null;
let oriiButton = null;
let sessionId = generateSessionId();
let sidebarOpen = false; // Track sidebar state

// Main initialization function
function initializeOriiSidebar() {
  // Check if we're on Google Calendar
  if (!isGoogleCalendar()) return;

  // Check if sidebar is already injected
  if (oriiButton) return;

  console.log("🔍 ORII: Starting initialization...");
  console.log("🔍 ORII: Current URL:", window.location.href);

  // Debug: Log all possible sidebar containers
  debugGoogleCalendarStructure();

  // Find the right sidebar container in Google Calendar
  const rightSidebar = findRightSidebarContainer();
  if (!rightSidebar) {
    console.error(
      "❌ ORII: Could not find right sidebar container in Google Calendar"
    );
    return;
  }
  console.log("✅ ORII: Found right sidebar container:", rightSidebar);

  // Create ORII button for the sidebar
  oriiButton = createOriiButton();
  console.log("✅ ORII: Created button element:", oriiButton);

  // Find the sidebar button container
  const buttonContainer = findSidebarButtonContainer();
  if (!buttonContainer) {
    console.error("❌ ORII: Could not find sidebar button container");
    return;
  }
  console.log("✅ ORII: Found sidebar button container:", buttonContainer);

  // Add the button to the container
  buttonContainer.appendChild(oriiButton);
  console.log("✅ ORII: Added button to container");

  // Create sidebar container (initially hidden)
  sidebarContainer = createSidebarContainer();

  // Attach directly to body instead of Google Calendar's sidebar to avoid hiding
  document.body.appendChild(sidebarContainer);
  console.log("✅ ORII: Created and added sidebar container to body");
  console.log(
    "🔍 ORII: Sidebar container parent:",
    sidebarContainer.parentElement
  );
  console.log(
    "🔍 ORII: Document body contains sidebar:",
    document.body.contains(sidebarContainer)
  );

  // Add click event listener to the button
  oriiButton.addEventListener("click", toggleSidebar);
  console.log("✅ ORII: Added click event listener");

  // Load sidebar content
  loadSidebarContent();

  console.log("🎉 ORII: Calendar Assistant sidebar initialized successfully!");
}

// Helper function to check if we're on Google Calendar
function isGoogleCalendar() {
  return window.location.href.includes("calendar.google.com");
}

// Debug function to analyze Google Calendar's DOM structure
function debugGoogleCalendarStructure() {
  console.log("🔍 ORII: Debugging Google Calendar DOM structure...");

  // Check for various sidebar-related elements
  const potentialSidebars = [
    'div[role="complementary"]',
    '[data-sidebar="true"]',
    ".nH.L5.xK",
    "div.a2DcO",
    "[jsname]",
    "[jscontroller]",
    ".FUcGRb", // Common Google Calendar class
    ".KtaFec", // Another common class
    ".h7JTQ", // Another potential sidebar class
  ];

  potentialSidebars.forEach((selector) => {
    const elements = document.querySelectorAll(selector);
    if (elements.length > 0) {
      console.log(
        `✅ Found ${elements.length} elements for selector "${selector}":`,
        elements
      );
    } else {
      console.log(`❌ No elements found for selector "${selector}"`);
    }
  });

  // Check for button containers
  const potentialButtonContainers = [
    'div[role="tablist"]',
    ".Y4.jCf",
    ".oo3Gd",
    "[data-tabs]",
    ".VfPpkd-AznF2e", // Material Design button container
    '[jsaction*="click"]',
  ];

  potentialButtonContainers.forEach((selector) => {
    const elements = document.querySelectorAll(selector);
    if (elements.length > 0) {
      console.log(
        `✅ Found ${elements.length} button containers for selector "${selector}":`,
        elements
      );
    } else {
      console.log(`❌ No button containers found for selector "${selector}"`);
    }
  });

  // Check for any element that looks like it could be a sidebar
  const allDivs = document.querySelectorAll("div");
  let sidebarCandidates = [];

  allDivs.forEach((div) => {
    const rect = div.getBoundingClientRect();
    // Look for tall, narrow elements on the right side of the screen
    if (
      rect.height > 400 &&
      rect.width < 500 &&
      rect.right > window.innerWidth - 600
    ) {
      sidebarCandidates.push({
        element: div,
        rect: rect,
        classes: div.className,
        id: div.id,
      });
    }
  });

  if (sidebarCandidates.length > 0) {
    console.log(
      "🎯 ORII: Potential sidebar candidates based on positioning:",
      sidebarCandidates
    );
  }
}

// Find the right sidebar container in Google Calendar
function findRightSidebarContainer() {
  // Google Calendar's right sidebar structure changes occasionally
  // We'll try a few different selectors
  const selectors = ['div[role="complementary"]', ".nH.L5.xK", "div.a2DcO"];

  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (element) return element;
  }

  return null;
}

// Find container for sidebar buttons
function findSidebarButtonContainer() {
  // Google Calendar's sidebar button container
  const selectors = ['div[role="tablist"]', ".Y4.jCf", ".oo3Gd"];

  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (element) return element;
  }

  return null;
}

// Create ORII button
function createOriiButton() {
  const button = document.createElement("div");
  button.className = "orii-sidebar-button";
  button.setAttribute("role", "tab");
  button.setAttribute("title", "ORII Calendar Assistant");

  // Style the button to match Google Calendar's design
  button.style.cssText = `
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    margin: 4px 0;
    border-radius: 24px;
    transition: background-color 0.2s ease;
    position: relative;
  `;

  // Add hover effects
  button.addEventListener("mouseenter", () => {
    if (!sidebarOpen) {
      button.style.backgroundColor = "#f1f3f4";
    }
  });

  button.addEventListener("mouseleave", () => {
    if (!sidebarOpen) {
      button.style.backgroundColor = "transparent";
    }
  });

  // Create the ORII logo/icon
  const icon = document.createElement("div");
  icon.innerHTML = `
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" stroke="#5f6368" stroke-width="2" fill="none"/>
      <path d="M8 12h8M12 8v8" stroke="#5f6368" stroke-width="2" stroke-linecap="round"/>
      <text x="12" y="16" text-anchor="middle" fill="#5f6368" font-size="6" font-family="Google Sans, sans-serif">AI</text>
    </svg>
  `;

  button.appendChild(icon);
  return button;
}

// Create sidebar container
function createSidebarContainer() {
  const container = document.createElement("div");
  container.className = "orii-sidebar-container";

  // Style the container to integrate seamlessly with Google Calendar
  container.style.cssText = `
    display: none;
    position: fixed;
    top: 64px;
    right: 0;
    height: calc(100vh - 64px);
    width: 360px;
    background-color: #ffffff;
    box-shadow: -1px 0 4px rgba(0, 0, 0, 0.1);
    z-index: 1000;
    border-left: 1px solid #dadce0;
    font-family: 'Google Sans', Roboto, Arial, sans-serif;
  `;

  return container;
}

// Toggle sidebar visibility
function toggleSidebar() {
  console.log("🔄 ORII: Toggling sidebar...");
  console.log("🔄 ORII: Current state - sidebarOpen:", sidebarOpen);

  if (!sidebarOpen) {
    openSidebar();
  } else {
    closeSidebar();
  }
}

// Open sidebar
function openSidebar() {
  console.log("📖 ORII: Opening sidebar");
  sidebarOpen = true;

  // Open sidebar with smooth animation
  sidebarContainer.style.display = "block";
  sidebarContainer.style.opacity = "0";
  sidebarContainer.style.transform = "translateX(100%)";

  // Animate in
  setTimeout(() => {
    sidebarContainer.style.transition = "all 0.3s ease";
    sidebarContainer.style.opacity = "1";
    sidebarContainer.style.transform = "translateX(0)";
  }, 10);

  // Add active state to button
  if (oriiButton) {
    oriiButton.style.backgroundColor = "#e8f0fe";
    oriiButton.style.borderRadius = "24px";
  }

  // Check if iframe exists and notify it
  const iframe = sidebarContainer.querySelector("iframe");
  if (iframe) {
    console.log("✅ ORII: Iframe found in sidebar");

    // Notify iframe that sidebar is now visible
    setTimeout(() => {
      try {
        iframe.contentWindow.postMessage(
          {
            action: "sidebarVisible",
            visible: true,
          },
          "*"
        );
        console.log("📤 ORII: Sent visibility notification to iframe");
      } catch (error) {
        console.warn("⚠️ ORII: Could not send message to iframe:", error);
      }
    }, 100);
  }
}

// Close sidebar
function closeSidebar() {
  console.log("📕 ORII: Closing sidebar");
  sidebarOpen = false;

  // Close sidebar with smooth animation
  sidebarContainer.style.transition = "all 0.3s ease";
  sidebarContainer.style.opacity = "0";
  sidebarContainer.style.transform = "translateX(100%)";

  setTimeout(() => {
    sidebarContainer.style.display = "none";
  }, 300);

  // Remove active state from button
  if (oriiButton) {
    oriiButton.style.backgroundColor = "transparent";
  }
}

// Load sidebar content
function loadSidebarContent() {
  console.log("🔄 ORII: Loading sidebar content...");

  // Create iframe to load sidebar.html
  const iframe = document.createElement("iframe");
  iframe.src = chrome.runtime.getURL("sidebar.html");

  // Clean, minimal iframe styling
  iframe.style.cssText = `
    width: 100%;
    height: 100%;
    border: none;
    background-color: transparent;
  `;

  // Add load event listener to iframe
  iframe.addEventListener("load", function () {
    console.log("✅ ORII: Sidebar iframe loaded successfully");
  });

  iframe.addEventListener("error", function (error) {
    console.error("❌ ORII: Error loading sidebar iframe:", error);
  });

  console.log("🔄 ORII: Adding iframe to sidebar container...");
  sidebarContainer.appendChild(iframe);
  console.log("✅ ORII: Iframe added to sidebar container");

  // Set up message passing between iframe and content script
  window.addEventListener("message", handleIframeMessage);
  console.log("✅ ORII: Message listener added for iframe communication");
}

// Handle messages from iframe
function handleIframeMessage(event) {
  // Verify message source
  const iframe = sidebarContainer.querySelector("iframe");
  if (!iframe || event.source !== iframe.contentWindow) {
    return;
  }

  const message = event.data;
  console.log("🔄 CONTENT: Received message from iframe:", message);

  // Handle close sidebar request
  if (message.action === "closeSidebar") {
    console.log("🔄 CONTENT: Closing sidebar from iframe request");
    closeSidebar(); // Specifically close the sidebar
    return;
  }

  // Handle user query
  if (message.action === "processQuery") {
    console.log("🔄 CONTENT: Processing query:", message.query);

    chrome.runtime.sendMessage(
      {
        action: "processQuery",
        query: message.query,
        sessionId: sessionId,
      },
      (response) => {
        console.log("🔄 CONTENT: Received response from background:", response);
        console.log("🔄 CONTENT: Response type:", typeof response);
        console.log("🔄 CONTENT: Response status:", response?.status);
        console.log("🔄 CONTENT: Response data:", response?.data);

        // Send response back to iframe - be very defensive about this
        try {
          const iframe = sidebarContainer.querySelector("iframe");
          if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage(
              {
                action: "queryResponse",
                response: response,
              },
              "*"
            );
            console.log("✅ CONTENT: Successfully sent response to iframe");
          } else {
            console.error(
              "❌ CONTENT: Iframe not found when trying to send response"
            );
          }
        } catch (error) {
          console.error("❌ CONTENT: Error sending message to iframe:", error);
        }
      }
    );
  }

  // Handle authentication request
  if (message.action === "authenticate") {
    chrome.runtime.sendMessage(
      {
        action: "authenticate",
      },
      (response) => {
        // Send response back to iframe
        sidebarContainer.querySelector("iframe").contentWindow.postMessage(
          {
            action: "authResponse",
            response: response,
          },
          "*"
        );
      }
    );
  }
}

// Generate a unique session ID
function generateSessionId() {
  return "orii-" + Date.now() + "-" + Math.floor(Math.random() * 1000000);
}

// Initialize when page is fully loaded
window.addEventListener("load", function () {
  console.log("🚀 ORII: Window load event fired");
  initializeOriiSidebar();
});

// Also try to initialize on DOM content loaded (in case load is delayed)
document.addEventListener("DOMContentLoaded", function () {
  console.log("🚀 ORII: DOM content loaded event fired");
  initializeOriiSidebar();
});

// Re-check periodically in case Calendar's UI updates dynamically
setInterval(function () {
  console.log("🔄 ORII: Periodic check running...");
  initializeOriiSidebar();
}, 5000);
