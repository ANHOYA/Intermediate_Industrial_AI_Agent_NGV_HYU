import { KEYS } from '../types';

/**
 * Sends image to local Python API for processing.
 * No API Key required on frontend (handled by Python backend).
 */
export const observeImage = async (imgUrl: string, strict: boolean) => {
  // Call local Python Server
  const SERVER_URL = "http://localhost:8000/analyze";

  // Generate dummy ID for the server request
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
    const hasDefect = data.label === 1;

    const obs: Record<string, boolean> = {};
    KEYS.forEach(k => { obs[k] = false; });

    if (hasDefect) {
      // Mark 'package_damage' as true to signal defect to the frontend logic
      // This maps the single boolean result back to the detailed map structure
      obs['package_damage'] = true;
    }

    return obs;

  } catch (e) {
    console.error("Agent Server Failed:", e);
    throw e;
  }
};