import { BRIDGE_URL, MODEL, buildPrompt, SYSTEM_PROMPT } from '../constants';
import { KEYS } from '../types';

interface ChatMessage {
  role: 'system' | 'user';
  content: string | Array<{ type: string; text?: string; image_url?: { url: string } }>;
}

export const postChat = async (messages: ChatMessage[], apiKey: string): Promise<string> => {
  try {
    // Sanitize API Key (remove potential quotes loaded from env)
    const cleanApiKey = apiKey.replace(/^['"]|['"]$/g, '');
    console.debug("Saltlux API Request:", { BRIDGE_URL, cleanApiKey, messages });
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
      const errorText = await response.text();
      throw new Error(`API Error ${response.status}: ${errorText}`);
    }

    const data = await response.json();
    return data.choices[0].message.content.trim();
  } catch (error: any) {
    console.error("API Call Failed:", error);
    throw error;
  }
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
  const promptText = buildPrompt(strict);
  const messages: ChatMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    {
      role: "user",
      content: [
        { type: "text", text: promptText },
        { type: "image_url", image_url: { url: imgUrl } }
      ]
    }
  ];

  const content = await postChat(messages, apiKey);
  const rawObs = safeJsonExtract(content);

  // Normalize
  const obs: Record<string, boolean> = {};
  KEYS.forEach(k => {
    obs[k] = Boolean(rawObs[k]);
  });

  return obs;
};