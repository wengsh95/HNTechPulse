import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";

const PATCHES_FILE = path.resolve(__dirname, "style_patches.json");

/** 提供读取/保存 style_patches.json 的 API */
function stylePatchesPlugin() {
  return {
    name: "style-patches-api",
    configureServer(server: any) {
      // GET  /api/style-patches → 返回当前补丁文件
      // POST /api/style-patches → 保存补丁到磁盘
      server.middlewares.use("/api/style-patches", (req: any, res: any) => {
        res.setHeader("Access-Control-Allow-Origin", "*");
        res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        res.setHeader("Access-Control-Allow-Headers", "Content-Type");

        if (req.method === "OPTIONS") {
          res.statusCode = 204;
          res.end();
          return;
        }

        if (req.method === "GET") {
          try {
            if (fs.existsSync(PATCHES_FILE)) {
              const data = fs.readFileSync(PATCHES_FILE, "utf-8");
              res.setHeader("Content-Type", "application/json");
              res.end(data);
            } else {
              res.setHeader("Content-Type", "application/json");
              res.end("{}");
            }
          } catch (e: any) {
            res.statusCode = 500;
            res.end(JSON.stringify({ error: e.message }));
          }
          return;
        }

        if (req.method === "POST") {
          let body = "";
          req.on("data", (chunk: string) => { body += chunk; });
          req.on("end", () => {
            try {
              const parsed = JSON.parse(body);
              fs.mkdirSync(path.dirname(PATCHES_FILE), { recursive: true });
              fs.writeFileSync(PATCHES_FILE, JSON.stringify(parsed, null, 2), "utf-8");
              res.setHeader("Content-Type", "application/json");
              res.end(JSON.stringify({ ok: true }));
            } catch (e: any) {
              res.statusCode = 400;
              res.end(JSON.stringify({ error: e.message }));
            }
          });
          return;
        }

        res.statusCode = 405;
        res.end("Method Not Allowed");
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), stylePatchesPlugin()],
  server: {
    port: 3002,
    open: true,
  },
  build: {
    outDir: "dist",
  },
  esbuild: {
    jsxFactory: "React.createElement",
    jsxFragment: "React.Fragment",
  },
});
