import { OBS_ITEMS } from './types';

// @ts-ignore
export const DEFAULT_API_KEY = process.env.API_KEY || "2FsdGVkX19X953usgc0EhpzMqWH084Pdgr3GK+gWpOgYKHFM65EOQ0/czaUV7YeTpOZipFB8ljI5o9SFIUrTupKF+uudeCuxycL/yYBw6o/mxYpc+t8NooYKfRyamkpnoAPjd//xY1LorCyS1N5jE1nKZOCIFJjaYM50oD9G/J73+ugAClDpgdU7e96QZOe";

// Proxy path mapping to https://bridge.luxiacloud.com/llm/openai/chat/completions/gpt-4o-mini/create
export const BRIDGE_URL = "/api/luxia/llm/openai/chat/completions/gpt-4o-mini/create";
export const MODEL = "gpt-4o-mini-2024-07-18";

export const SYSTEM_PROMPT = `너는 반도체 소자 검사 이미지 분석기다.
반드시 요청한 JSON만 출력한다. 다른 텍스트는 절대 출력하지 않는다.`;

export const buildPrompt = (strict: boolean): string => {
  const header = `아래 항목을 이미지에서 관찰해 true/false로 채워 JSON만 출력해.
형식은 반드시 아래와 동일해야 한다.
`;

  const jsonTemplate = "{\n" + OBS_ITEMS.map(item => `  "${item.key}": false`).join(",\n") + "\n}";

  const rule = strict
    ? "\n판단 기준:\n- 매우 보수적으로 판단한다. 애매하면 무조건 false.\n"
    : "\n판단 기준:\n- 아주 명확할 때만 true. 애매하면 false.\n";

  const criteria = OBS_ITEMS.map(item => `- ${item.key}: ${item.desc}`).join("\n");

  return header + jsonTemplate + rule + criteria;
};

export const SAMPLE_CSV = `id,img_url
DEV_000,https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_000.png
DEV_001,https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_001.png
DEV_002,https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_002.png
DEV_003,https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_003.png
DEV_004,https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_004.png
DEV_005,https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_005.png`;