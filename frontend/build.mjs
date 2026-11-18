import * as esbuild from "esbuild";
import { mkdir, readFile, writeFile } from "node:fs/promises";
await mkdir("dist", { recursive: true });
const html = (await readFile("index.html", "utf8"))
  .replace("/index.tsx", "/assets/app.js")
  .replace(
    "</head>",
    '<link rel="stylesheet" href="/assets/app.css" /></head>',
  );
await writeFile("dist/index.html", html);
const options = {
  entryPoints: ["index.tsx"],
  bundle: true,
  outfile: "dist/assets/app.js",
  minify: true,
  sourcemap: false,
  target: ["es2022"],
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "info",
};
if (process.argv.includes("--watch")) {
  const context = await esbuild.context(options);
  await context.watch();
} else await esbuild.build(options);
