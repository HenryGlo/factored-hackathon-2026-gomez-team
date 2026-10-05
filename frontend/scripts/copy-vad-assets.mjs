// Copia a public/vad/ los archivos que el VAD del modo voz carga en el navegador (modelo Silero, worklet y ONNX Runtime en
// WASM). Los sirve la propia app: nada viene de un CDN. Corre antes de `dev` y de `build` (predev / prebuild).
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "vad");
mkdirSync(out, { recursive: true });
const files = [
  ["node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx", "silero_vad_v5.onnx"],
  ["node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js", "vad.worklet.bundle.min.js"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.wasm"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.mjs"],
];
for (const [from, to] of files) copyFileSync(join(root, from), join(out, to));
console.log(`VAD: ${files.length} archivos en public/vad/`);
