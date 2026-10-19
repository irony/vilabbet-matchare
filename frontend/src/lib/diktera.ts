/**
 * Diktering via Bergets realtime-transkribering (klang/pianissimo).
 * Ljudet går PCM16 24 kHz över WebSocket till serverns /api/realtime-relä
 * (som håller nyckeln) — partiell text strömmar medan man pratar.
 */

export type DikteraStatus = "lyssnar" | "stoppad" | "fel";

export interface DikteraCallbacks {
  onPartial: (text: string) => void;
  onFinal: (text: string) => void;
  onStatus: (status: DikteraStatus) => void;
}

function floatTo16BitPCM(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

function toBase64(buffer: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function resample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) out[i] = input[Math.floor(i * ratio)];
  return out;
}

/** Startar mikrofon + websocket. Returnerar en stopp-funktion. */
export async function startaDiktering(cb: DikteraCallbacks): Promise<() => void> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/realtime?model=klang/pianissimo`);
  const ctx = new AudioContext({ sampleRate: 24000 });
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  let partial = "";
  let stoppad = false;

  const stoppa = () => {
    if (stoppad) return;
    stoppad = true;
    try { ws.close(); } catch { /* redan stängd */ }
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close();
    cb.onStatus("stoppad");
  };

  ws.onmessage = (e) => {
    const ev = JSON.parse(String(e.data));
    if (ev.type === "session.created") {
      ws.send(
        JSON.stringify({
          type: "session.update",
          session: {
            type: "transcription",
            audio: {
              input: {
                format: { type: "audio/pcm", rate: 24000 },
                transcription: { model: "klang/pianissimo", languages: ["sv"] },
                turn_detection: { type: "server_vad" },
              },
            },
          },
        }),
      );
      cb.onStatus("lyssnar");
      return;
    }
    if (ev.type === "conversation.item.input_audio_transcription.delta") {
      partial += ev.delta ?? "";
      cb.onPartial(partial);
      return;
    }
    if (ev.type === "conversation.item.input_audio_transcription.completed") {
      const t = String(ev.transcript ?? "").trim();
      if (t) cb.onFinal(t);
      partial = "";
      cb.onPartial("");
      return;
    }
    if (ev.type === "error") cb.onStatus("fel");
  };
  ws.onerror = () => {
    if (!stoppad) {
      cb.onStatus("fel");
      stoppa();
    }
  };
  ws.onclose = () => {
    if (!stoppad) {
      cb.onStatus("fel");
      stoppa();
    }
  };

  processor.onaudioprocess = (e) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    const channel = e.inputBuffer.getChannelData(0);
    const pcm = floatTo16BitPCM(resample(channel, ctx.sampleRate, 24000));
    ws.send(JSON.stringify({ type: "input_audio_buffer.append", audio: toBase64(pcm) }));
  };
  source.connect(processor);
  processor.connect(ctx.destination);

  return stoppa;
}

/** Mejl/url-diktering: "christian snabel-a berget punkt ai" → "christian@berget.ai" */
export function tillAdress(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s*snabel[\s-]?a\s*/g, "@")
    .replace(/\s*punkt\s*/g, ".")
    .replace(/\s*streck\s*/g, "-")
    .replace(/\s+/g, "");
}
