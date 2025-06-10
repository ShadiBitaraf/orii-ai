// ORII Calendar Assistant - Background Script

// Configuration

const API_BASE_URL = "http://localhost:8000"; // Local development server
// For production: const API_BASE_URL = "https://orii-ai-production.up.railway.app";

// Store authentication state
let authToken = null;

// Handle extension installation
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log("ORII Calendar Assistant installed:", details.reason);

  try {
    // Set up side panel to open when action icon is clicked
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
    console.log("✅ BACKGROUND: Side panel behavior set");

    // Set up default side panel (works on all sites)
    await chrome.sidePanel.setOptions({
      path: "sidebar.html",
      enabled: true,
    });
    console.log("✅ BACKGROUND: Default side panel configured");
  } catch (error) {
    console.error("❌ BACKGROUND: Error during installation:", error);
  }
});

// Side panel is now globally available - no need for tab-specific logic

// Listen for messages from side panel
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "initializeSidebar") {
    console.log("Initializing sidebar");
    sendResponse({ status: "success" });
  }

  if (message.action === "processQuery") {
    processUserQuery(message.query, message.sessionId)
      .then((response) => {
        sendResponse({ status: "success", data: response });
      })
      .catch((error) => {
        console.error("Error processing query:", error);
        sendResponse({
          status: "error",
          error: error.message || "Unknown error occurred",
        });
      });
    return true; // Required for async sendResponse
  }

  if (message.action === "authenticate") {
    initiateOAuth()
      .then((token) => {
        authToken = token;
        sendResponse({ status: "success", authenticated: true });
      })
      .catch((error) => {
        console.error("Authentication error:", error);
        sendResponse({
          status: "error",
          error: error.message || "Authentication failed",
        });
      });
    return true; // Required for async sendResponse
  }
});

// Process user query through backend API
async function processUserQuery(query, sessionId) {
  try {
    console.log(
      "🔄 BACKGROUND: Making request to:",
      `${API_BASE_URL}/api/query`
    );
    console.log("🔄 BACKGROUND: Request payload:", {
      query,
      session_id: sessionId,
    });

    const response = await fetch(`${API_BASE_URL}/api/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authToken ? `Bearer ${authToken}` : "",
      },
      body: JSON.stringify({
        query: query,
        session_id: sessionId,
      }),
    });

    console.log("🔄 BACKGROUND: Response status:", response.status);
    console.log("🔄 BACKGROUND: Response ok:", response.ok);

    if (!response.ok) {
      // Try to get error message, but handle non-JSON responses
      let errorMessage = `Server error: ${response.status}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorMessage;
      } catch (jsonError) {
        // If it's not JSON, get the text response
        try {
          const textResponse = await response.text();
          errorMessage = textResponse || errorMessage;
        } catch (textError) {
          // Keep the default error message
        }
      }
      throw new Error(errorMessage);
    }

    const jsonData = await response.json();
    console.log("🔄 BACKGROUND: Parsed JSON data:", jsonData);
    console.log("🔄 BACKGROUND: Returning to side panel");

    return jsonData;
  } catch (error) {
    console.error("❌ BACKGROUND: API request failed:", error);
    throw error;
  }
}

// Initiate OAuth flow
async function initiateOAuth() {
  return new Promise((resolve, reject) => {
    //     const clientId = chrome.runtime.getManifest().oauth2.client_id;
    //     const scopes = chrome.runtime.getManifest().oauth2.scopes;
    const manifest = chrome.runtime.getManifest();

    // Check if OAuth is configured in manifest
    if (!manifest.oauth2 || !manifest.oauth2.client_id) {
      console.log("OAuth not configured in manifest. Skipping authentication.");
      resolve(null);
      return;
    }

    const clientId = manifest.oauth2.client_id;
    const scopes = manifest.oauth2.scopes;

    const authUrl = new URL("https://accounts.google.com/o/oauth2/auth");
    authUrl.searchParams.set("client_id", clientId);
    authUrl.searchParams.set("response_type", "token");
    authUrl.searchParams.set("redirect_uri", chrome.identity.getRedirectURL());
    authUrl.searchParams.set("scope", scopes.join(" "));

    chrome.identity.launchWebAuthFlow(
      { url: authUrl.toString(), interactive: true },
      (responseUrl) => {
        if (chrome.runtime.lastError) {
          return reject(chrome.runtime.lastError);
        }

        if (!responseUrl) {
          return reject(new Error("Authentication failed"));
        }

        // Extract access token from response URL
        const url = new URL(responseUrl);
        const params = new URLSearchParams(url.hash.substring(1));
        const accessToken = params.get("access_token");

        if (!accessToken) {
          return reject(new Error("No access token found in response"));
        }

        // Store the token
        resolve(accessToken);
      }
    );
  });
}
