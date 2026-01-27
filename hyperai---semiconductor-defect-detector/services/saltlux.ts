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

    const hasDefect = data.label === 1;
    const obs: Record<string, boolean> = {};
    KEYS.forEach(k => { obs[k] = false; });

    if (hasDefect) {
      // Map returned details to obs keys
      if (data.details && typeof data.details === 'object') {
        Object.keys(data.details).forEach(k => {
          // Ensure key exists in our defined KEYS (defect_package, defect_pin)
          // and value is truthy
          if ((KEYS as unknown as string[]).includes(k) && data.details[k]) {
            obs[k] = true;
          }
        });
      }

      // Fallback: If label is 1 but no details matched (e.g. edge case), 
      // check if any key was set. If not, maybe defaulting is safer?
      // But agent.py is designed to return details now.
      // Let's at least log if mismatch happens
      const anySet = Object.values(obs).some(v => v);
      if (!anySet) {
        console.warn("Server returned label=1 but no recognized details keys. data:", data);
      }
    }

    return obs;

  } catch (e) {
    console.error("Agent Server Failed:", e);
    throw e;
  }
};