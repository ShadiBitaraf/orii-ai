// ORII Calendar Assistant - Sidebar Script

// DOM elements
const messagesContainer = document.getElementById("messagesContainer");
const userInput = document.getElementById("userInput");
const sendButton = document.getElementById("sendButton");
const closeButton = document.getElementById("closeButton");

// State
let isWaitingForResponse = false;
let authenticated = false;

// Helper function for smooth scrolling to bottom
function scrollToBottom() {
  if (messagesContainer) {
    // Use both scrollTop and scrollIntoView for better compatibility
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // Also ensure the last message is visible
    const lastMessage = messagesContainer.lastElementChild;
    if (lastMessage) {
      lastMessage.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }
}

// Initialize the sidebar
function initializeSidebar() {
  console.log("🚀 ORII SIDEBAR: Initializing sidebar...");

  // Check if DOM elements exist
  if (!messagesContainer) {
    console.error("❌ ORII SIDEBAR: Messages container not found");
    return;
  }
  if (!userInput) {
    console.error("❌ ORII SIDEBAR: User input not found");
    return;
  }
  if (!sendButton) {
    console.error("❌ ORII SIDEBAR: Send button not found");
    return;
  }
  if (!closeButton) {
    console.error("❌ ORII SIDEBAR: Close button not found");
    console.log("🔍 ORII SIDEBAR: Available elements:", {
      messagesContainer: !!messagesContainer,
      userInput: !!userInput,
      sendButton: !!sendButton,
      closeButton: !!closeButton,
    });
    console.log(
      "🔍 ORII SIDEBAR: Document body HTML:",
      document.body.innerHTML
    );
    return;
  }

  console.log("✅ ORII SIDEBAR: All DOM elements found");
  console.log("🔍 ORII SIDEBAR: Close button element:", closeButton);

  // Add event listeners
  sendButton.addEventListener("click", handleSendMessage);
  console.log("✅ ORII SIDEBAR: Send button click listener added");

  closeButton.addEventListener("click", handleCloseButton);
  console.log("✅ ORII SIDEBAR: Close button click listener added");

  // Test close button directly
  closeButton.addEventListener("click", function () {
    console.log("🔄 ORII SIDEBAR: Close button clicked - direct listener test");
  });

  userInput.addEventListener("keydown", (event) => {
    // Send message on Enter (but not Shift+Enter for new lines)
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }

    // Auto-resize textarea
    setTimeout(() => {
      userInput.style.height = "auto";
      userInput.style.height = Math.min(userInput.scrollHeight, 120) + "px";
    }, 0);
  });
  console.log("✅ ORII SIDEBAR: User input event listeners added");

  console.log("✅ ORII SIDEBAR: Sidebar initialized successfully");
}

// Handle sending messages
function handleSendMessage() {
  const query = userInput.value.trim();

  // Validate input
  if (!query || isWaitingForResponse) return;

  // Clear input
  userInput.value = "";
  userInput.style.height = "auto";

  // Add user message to chat
  addMessageToChat("user", query);

  // Show loading indicator
  addLoadingIndicator();
  isWaitingForResponse = true;

  // Check if authentication is needed
  if (!authenticated) {
    authenticate()
      .then(() => {
        processQuery(query);
      })
      .catch((error) => {
        removeLoadingIndicator();
        isWaitingForResponse = false;
        addMessageToChat(
          "system",
          `Authentication error: ${error.message || "Failed to authenticate"}`
        );
      });
  } else {
    // Process the query
    processQuery(query);
  }
}

// Process user query
function processQuery(query) {
  // Send message to content script
  window.parent.postMessage(
    {
      action: "processQuery",
      query: query,
    },
    "*"
  );
}

// Check authentication status
function checkAuthentication() {
  // Send message to content script
  window.parent.postMessage(
    {
      action: "authenticate",
    },
    "*"
  );
}

// Authenticate with Google
function authenticate() {
  return new Promise((resolve, reject) => {
    // Add auth message to chat
    // addMessageToChat(
    //   "system",
    //   "Please sign in with your Google account to access your calendar."
    // );

    // Send auth request to content script
    window.parent.postMessage(
      {
        action: "authenticate",
      },
      "*"
    );

    // Set timeout for auth response
    const authTimeout = setTimeout(() => {
      reject(new Error("Authentication timed out"));
    }, 60000); // 1 minute timeout

    // One-time listener for auth response
    const authResponseListener = (event) => {
      const message = event.data;

      if (message.action === "authResponse") {
        clearTimeout(authTimeout);
        window.removeEventListener("message", authResponseListener);

        if (message.response.status === "success") {
          authenticated = true;
          resolve();
        } else {
          reject(new Error(message.response.error || "Authentication failed"));
        }
      }
    };

    window.addEventListener("message", authResponseListener);
  });
}

// Add message to chat
function addMessageToChat(type, content) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `message ${type}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";
  contentDiv.textContent = content;

  messageDiv.appendChild(contentDiv);
  messagesContainer.appendChild(messageDiv);

  // Scroll to bottom with slight delay to ensure rendering
  setTimeout(() => {
    scrollToBottom();
  }, 10);
}

// Add loading indicator
function addLoadingIndicator() {
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "message system loading-message";

  const loadingContent = document.createElement("div");
  loadingContent.className = "loading";

  // Create dots
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement("div");
    dot.className = "dot";
    loadingContent.appendChild(dot);
  }

  loadingDiv.appendChild(loadingContent);
  messagesContainer.appendChild(loadingDiv);

  // Scroll to bottom with slight delay to ensure rendering
  setTimeout(() => {
    scrollToBottom();
  }, 10);
}

// Remove loading indicator
function removeLoadingIndicator() {
  const loadingMessage = messagesContainer.querySelector(".loading-message");
  if (loadingMessage) {
    messagesContainer.removeChild(loadingMessage);
  }
}

// Handle incoming messages from content script
function handleIncomingMessage(event) {
  console.log("📨 ORII SIDEBAR: Received message:", event.data);
  const message = event.data;

  if (message.action === "sidebarVisible") {
    console.log("👁️ ORII SIDEBAR: Sidebar is now visible!");
    // Add a visual confirmation that the sidebar is working
    // addMessageToChat(
    //   "system",
    //   "🎉 ORII sidebar is now active! Type your message below to get started."
    // );
    return;
  }

  if (message.action === "queryResponse") {
    // Remove loading indicator
    removeLoadingIndicator();
    isWaitingForResponse = false;

    const response = message.response;

    // Debug logging to see the exact response structure
    console.log("🔍 ORII SIDEBAR: Full response received:", response);
    console.log("🔍 ORII SIDEBAR: Response status:", response?.status);
    console.log("🔍 ORII SIDEBAR: Response data:", response?.data);

    try {
      if (response && response.status === "success") {
        // Try different possible response structures
        let responseText = "";

        if (response.data && response.data.response) {
          // Structure: { status: "success", data: { response: "text" } }
          responseText = response.data.response;
          console.log(
            "✅ ORII SIDEBAR: Using response.data.response:",
            responseText
          );
        } else if (response.data && typeof response.data === "string") {
          // Structure: { status: "success", data: "text" }
          responseText = response.data;
          console.log("✅ ORII SIDEBAR: Using response.data:", responseText);
        } else if (response.response) {
          // Structure: { status: "success", response: "text" }
          responseText = response.response;
          console.log(
            "✅ ORII SIDEBAR: Using response.response:",
            responseText
          );
        } else {
          responseText = "Response received but format was unexpected";
          console.warn("⚠️ ORII SIDEBAR: Unexpected response format");
        }

        addMessageToChat("system", responseText);
      } else {
        // Handle error response
        const errorMsg =
          response?.error || response?.data?.error || "Unknown error occurred";
        console.error("❌ ORII SIDEBAR: Error response:", errorMsg);
        addMessageToChat("system", `Error: ${errorMsg}`);
      }
    } catch (error) {
      console.error("❌ ORII SIDEBAR: Error processing response:", error);
      addMessageToChat(
        "system",
        "Sorry, there was an error processing the response."
      );
    }
  }

  if (message.action === "authResponse") {
    if (message.response.status === "success") {
      authenticated = true;
    }
  }
}

// Set up message handler
window.addEventListener("message", handleIncomingMessage);
console.log("✅ ORII SIDEBAR: Message handler set up");

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  console.log("🚀 ORII SIDEBAR: DOM content loaded, calling initializeSidebar");
  initializeSidebar();
});

console.log(
  "📄 ORII SIDEBAR: Script loaded, waiting for DOM content loaded..."
);

// Handle close button click
function handleCloseButton() {
  console.log("🔄 ORII SIDEBAR: Close button clicked");
  console.log("🔄 ORII SIDEBAR: window.parent:", window.parent);
  console.log("🔄 ORII SIDEBAR: Sending closeSidebar message...");

  // Send message to parent to close sidebar
  try {
    window.parent.postMessage(
      {
        action: "closeSidebar",
      },
      "*"
    );
    console.log("✅ ORII SIDEBAR: Message sent successfully");
  } catch (error) {
    console.error("❌ ORII SIDEBAR: Error sending close message:", error);
  }
}
