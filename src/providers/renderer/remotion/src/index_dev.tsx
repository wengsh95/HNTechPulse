/* ================================================================
   Dev Entry Point — 独立预览服务器
   运行方式: cd remotion && npx vite
   访问: http://localhost:3002
   ================================================================ */

import React from "react";
import { createRoot } from "react-dom/client";
import { DevPreview } from "./Components/DevPreview";

createRoot(document.getElementById("root")!).render(<DevPreview />);