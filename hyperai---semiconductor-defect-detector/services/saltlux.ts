import { BRIDGE_URL, MODEL, buildPrompt, SYSTEM_PROMPT } from '../constants';
import { KEYS } from '../types';

interface ChatMessage {
  role: 'system' | 'user';
  content: string | Array<{ type: string; text?: string; image_url?: { url: string } }>;
}

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export const postChat = async (messages: ChatMessage[], apiKey: string): Promise<string> => {
  const maxRetries = 10;
  let attempt = 0;

  while (attempt < maxRetries) {
    try {
      // Sanitize API Key (remove potential quotes loaded from env)
      const cleanApiKey = apiKey.replace(/^['"]|['"]$/g, '');
      console.debug(`Saltlux API Request (Attempt ${attempt + 1}/${maxRetries}):`, { BRIDGE_URL, cleanApiKey });

      const response = await fetch(BRIDGE_URL, {
        method: 'POST',
        headers: {
          'apikey': cleanApiKey,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: MODEL,
          messages: messages,
          max_tokens: 1024,
          stream: false
        })
      });

      if (!response.ok) {
        // If 500 or 400 (specifically timeout related)
        if (response.status >= 500 || response.status === 400 || response.status === 429) {
          const errorText = await response.text();
          console.warn(`API Error ${response.status} on attempt ${attempt + 1}: ${errorText}`);
          throw new Error(`API Error ${response.status}: ${errorText}`);
        }
        // Fatal client errors
        const errorText = await response.text();
        throw new Error(`Fatal API Error ${response.status}: ${errorText}`);
      }

      const data = await response.json();
      return data.choices[0].message.content.trim();

    } catch (error: any) {
      attempt++;
      console.error(`Attempt ${attempt} failed:`, error);

      if (attempt >= maxRetries) {
        throw error;
      }

      // Exponential backoff: 2s, 4s, 8s, 16s...
      const waitTime = Math.pow(2, attempt) * 1000;
      console.log(`Waiting ${waitTime}ms before retry...`);
      await delay(waitTime);
    }
  }
  throw new Error("Max retries exceeded");
};

export const safeJsonExtract = (text: string): Record<string, boolean> => {
  try {
    // Attempt standard parse
    return JSON.parse(text);
  } catch (e) {
    // Attempt regex extraction
    const match = text.match(/\{[\s\S]*\}/);
    if (match) {
      try {
        return JSON.parse(match[0]);
      } catch (innerE) {
        console.warn("Regex JSON extraction failed");
      }
    }
    console.error("Failed to parse JSON:", text);
    // Fallback: assume all false if parsing fails to avoid crashing
    const fallback: Record<string, boolean> = {};
    KEYS.forEach(k => { fallback[k] = false; });
    return fallback;
  }
};

export const observeImage = async (imgUrl: string, strict: boolean, apiKey: string) => {
  // Call local Python Server
  const SERVER_URL = "http://localhost:8000/analyze";

  // We use a dummy ID since `observeImage` signature doesn't pass ID, but server expects it.
  // Ideally we refactor `observeImage` to take an ID or generate one.
  const dummyId = "req_" + Math.random().toString(36).substring(7);

  try {
    const response = await fetch(SERVER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: dummyId,
        img_url: imgUrl
      })
    });

    if (!response.ok) {
      throw new Error(`Server Error: ${response.status}`);
    }

    const data = await response.json();

    // Transform server response to match expected `obs` format
    // Server returns "label": 1 (defect) or 0 (clean)
    // We map this back to implicit observation flags for compatibility
    const hasDefect = data.label === 1;

    // If defect, set a generic "defect_detected" flag to true
    // If clean, all false
    const obs: Record<string, boolean> = {};
    KEYS.forEach(k => { obs[k] = false; });

    if (hasDefect) {
      // Mark at least one as true to signal defect to the frontend logic
      obs['package_damage'] = true;
    }

    return obs;

  } catch (e) {
    console.error("Agent Server Failed:", e);
    throw e;
  }
};