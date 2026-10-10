// Optional: render composition.json to MP4 through Remotion (headless Chrome).
//
//   npm run render            # -> out/studio.mp4
//
// The Remotion renderer packages are optionalDependencies, so a normal
// `npm install` already provides them. The Python engine
// (`motion script.hmg --render --output out.mp4`) remains the primary,
// dependency-light renderer; this path is for Remotion-native pipelines,
// the edited timeline, and CI.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  let bundle, selectComposition, renderMedia;
  try {
    ({ bundle } = await import("@remotion/bundler"));
    ({ selectComposition, renderMedia } = await import("@remotion/renderer"));
  } catch (err) {
    console.error(
      "Missing Remotion renderer packages. Install them with:\n" +
        "  npm i -D @remotion/bundler @remotion/renderer\n"
    );
    process.exit(1);
  }

  const compPath = path.join(__dirname, "public", "composition.json");
  if (!fs.existsSync(compPath)) {
    console.error(
      `No composition found at ${compPath}.\n` +
        "Generate one with:  motion <script>.hmg --studio"
    );
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(compPath, "utf8"));

  console.log("Bundling studio…");
  const serveUrl = await bundle({
    entryPoint: path.join(__dirname, "src", "render-entry.tsx"),
  });

  const composition = await selectComposition({
    serveUrl,
    id: "MotionComposition",
    inputProps: { data },
  });

  const outDir = path.join(__dirname, "out");
  fs.mkdirSync(outDir, { recursive: true });
  const outputLocation = path.join(outDir, "studio.mp4");

  console.log(`Rendering ${composition.durationInFrames} frames…`);
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation,
    inputProps: { data },
  });
  console.log(`Done -> ${outputLocation}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
