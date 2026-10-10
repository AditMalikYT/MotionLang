/**
 * motionApi — dev-server backend for Motion Studio.
 *
 * Exposes the Export/Sync API used by the React editor so edited timelines
 * can be saved and re-rendered to MP4 without leaving the browser:
 *
 *   POST /api/composition      { composition }      -> saves public/composition.json
 *   POST /api/render           { composition? }     -> saves (if given) + starts a render job
 *   GET  /api/render                            -> list jobs
 *   GET  /api/render/:id                        -> job status + log tail
 *   GET  /api/download/:id                      -> streams the finished studio.mp4
 *
 * Rendering shells out to `npm run render` (Remotion headless Chrome), the
 * same pipeline as the CLI. Only active under `vite dev` (`apply: "serve"`),
 * so production builds are unaffected. No extra npm dependencies.
 */
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin, ViteDevServer } from "vite";

export type JobStatus = "queued" | "running" | "done" | "error";

export interface RenderJob {
  id: string;
  status: JobStatus;
  output: string | null;
  error: string | null;
  log: string[];
  startedAt: number;
  finishedAt: number | null;
}

const MAX_BODY_BYTES = 200 * 1024 * 1024;
const MAX_LOG_LINES = 300;

function readJsonBody(req: IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on("data", (c: Buffer) => {
      size += c.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("Request body too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"));
      } catch (e) {
        reject(new Error("Invalid JSON body"));
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res: ServerResponse, status: number, data: unknown) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function isComposition(value: any): boolean {
  return (
    value !== null &&
    typeof value === "object" &&
    typeof (value as any).meta === "object" &&
    Array.isArray((value as any).layers)
  );
}

export function motionApi(): Plugin {
  const studioRoot = process.cwd();
  const publicDir = path.join(studioRoot, "public");
  const outFile = path.join(studioRoot, "out", "studio.mp4");
  const jobs = new Map<string, RenderJob>();
  let counter = 0;

  const saveComposition = (composition: unknown): { layers: number; path: string } => {
    if (!isComposition(composition)) {
      throw new Error("Body must contain a composition { meta, layers }");
    }
    const dest = path.join(publicDir, "composition.json");
    fs.mkdirSync(publicDir, { recursive: true });
    fs.writeFileSync(dest, JSON.stringify(composition, null, 2));
    return { layers: (composition as any).layers.length, path: dest };
  };

  const pushLog = (job: RenderJob, line: string) => {
    job.log.push(line);
    if (job.log.length > MAX_LOG_LINES) {
      job.log.splice(0, job.log.length - MAX_LOG_LINES);
    }
  };

  const startRender = (job: RenderJob) => {
    job.status = "running";
    const npm = process.platform === "win32" ? "npm.cmd" : "npm";
    let child: ChildProcess;
    try {
      child = spawn(npm, ["run", "render"], {
        cwd: studioRoot,
        env: process.env,
        shell: false,
      });
    } catch (err: any) {
      job.status = "error";
      job.error = String(err?.message || err);
      job.finishedAt = Date.now();
      return;
    }
    pushLog(job, `$ npm run render (pid ${child.pid})`);
    child.stdout?.on("data", (d: Buffer) =>
      d.toString().split("\n").filter(Boolean).forEach((l) => pushLog(job, l))
    );
    child.stderr?.on("data", (d: Buffer) =>
      d.toString().split("\n").filter(Boolean).forEach((l) => pushLog(job, "ERR " + l))
    );
    child.on("error", (err) => {
      job.status = "error";
      job.error = String((err as Error)?.message || err);
      job.finishedAt = Date.now();
    });
    child.on("close", (code) => {
      job.finishedAt = Date.now();
      if (code === 0 && fs.existsSync(outFile)) {
        job.status = "done";
        job.output = outFile;
        pushLog(job, `Done -> ${outFile}`);
      } else {
        job.status = "error";
        job.error = `renderer exited with code ${code}`;
        pushLog(job, job.error);
      }
    });
  };

  return {
    name: "motion-studio-api",
    apply: "serve",
    configureServer(server: ViteDevServer) {
      server.middlewares.use("/api/composition", async (req, res) => {
        if (req.method !== "POST") {
          return sendJson(res, 405, { ok: false, error: "POST only" });
        }
        try {
          const body = await readJsonBody(req);
          const saved = saveComposition(body?.composition);
          return sendJson(res, 200, { ok: true, ...saved });
        } catch (err: any) {
          return sendJson(res, 400, { ok: false, error: String(err?.message || err) });
        }
      });

      server.middlewares.use("/api/render", async (req, res) => {
        const url = new URL(req.url || "/", "http://localhost");
        const parts = url.pathname.split("/").filter(Boolean); // [] or ["render"] or ["render", id]
        if (parts.length === 2 && parts[0] !== "render") {
          return sendJson(res, 404, { ok: false, error: "unknown job" });
        }
        const id = parts.length === 2 ? parts[1] : parts.length === 1 ? parts[0] : null;
        if (req.method === "POST" && id === null) {
          try {
            const body = await readJsonBody(req);
            if (body?.composition !== undefined) {
              saveComposition(body.composition);
            }
            const id = `job-${Date.now().toString(36)}-${counter++}`;
            const job: RenderJob = {
              id,
              status: "queued",
              output: null,
              error: null,
              log: [],
              startedAt: Date.now(),
              finishedAt: null,
            };
            jobs.set(id, job);
            startRender(job);
            return sendJson(res, 202, { ok: true, jobId: id, status: job.status });
          } catch (err: any) {
            return sendJson(res, 400, { ok: false, error: String(err?.message || err) });
          }
        }
        if (req.method === "GET" && id === null) {
          return sendJson(res, 200, {
            ok: true,
            jobs: [...jobs.values()].map((j) => ({
              id: j.id,
              status: j.status,
              output: j.output,
              error: j.error,
              startedAt: j.startedAt,
              finishedAt: j.finishedAt,
            })),
          });
        }
        if (req.method === "GET" && id !== null) {
          const job = jobs.get(id);
          if (!job) {
            return sendJson(res, 404, { ok: false, error: "unknown job" });
          }
          return sendJson(res, 200, { ok: true, ...job, log: job.log.slice(-60) });
        }
        return sendJson(res, 405, { ok: false, error: "method not allowed" });
      });

      server.middlewares.use("/api/download", (req, res) => {
        const url = new URL(req.url || "/", "http://localhost");
        const id = url.pathname.split("/").filter(Boolean)[0];
        const job = (id && jobs.get(id)) || null;
        const file = job?.output && fs.existsSync(job.output) ? job.output : null;
        if (!file) {
          return sendJson(res, 404, { ok: false, error: "no finished render for this job" });
        }
        const stat = fs.statSync(file);
        res.writeHead(200, {
          "Content-Type": "video/mp4",
          "Content-Length": stat.size,
          "Content-Disposition": `attachment; filename="motion-studio-${id}.mp4"`,
        });
        fs.createReadStream(file).pipe(res);
      });
    },
  };
}
