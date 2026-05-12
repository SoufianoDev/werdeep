/**
 * WeRDeep Tool - OpenCode Integration
 *
 * This module provides the tool definition for invoking WeRDeep
 * from OpenCode AI agents.
 */

import { Tool } from "@opencode-ai/plugin";

interface WeRDeepArgs {
  query: string;
  format?: "json" | "markdown" | "html" | "text";
  depth?: number;
  max_pages?: number;
  timeout?: number;
}

interface WeRDeepResult {
  status: "success" | "error";
  query: string;
  results: Array<{
    url: string;
    title?: string;
    content: string;
    depth: number;
    timestamp: string;
    links?: string[];
    metadata?: Record<string, unknown>;
    code_blocks?: Array<{
      type: string;
      language?: string;
      content: string;
      syntax_highlighted: boolean;
    }>;
  }>;
  metadata: {
    depth_achieved: number;
    pages_crawled: number;
    duration_ms: number;
    format: string;
    timestamp_start: string;
    timestamp_end: string;
  };
  error?: {
    code: string;
    message: string;
    action: string;
  };
}

export const werdeepTool: Tool = {
  name: "werdeep",
  description:
    "Deep web search and research tool for comprehensive content retrieval. Use this tool to crawl websites and extract structured content from multiple pages at varying depths.",
  parameters: {
    type: "object",
    properties: {
      query: {
        type: "string",
        description:
          "URL, keywords, or topic description to search. For URLs, provide the full URL (e.g., 'https://example.com').",
      },
      format: {
        type: "string",
        enum: ["json", "markdown", "html", "text"],
        default: "json",
        description: "Output format for results (default: json)",
      },
      depth: {
        type: "number",
        minimum: 1,
        maximum: 5,
        default: 3,
        description: "Crawl depth level (1-5, default: 3)",
      },
      max_pages: {
        type: "number",
        minimum: 1,
        maximum: 1000,
        default: 100,
        description: "Maximum pages to crawl (default: 100)",
      },
      timeout: {
        type: "number",
        minimum: 10,
        maximum: 3600,
        default: 300,
        description: "Timeout in seconds (default: 300)",
      },
    },
    required: ["query"],
  },

  async execute(args: WeRDeepArgs): Promise<string> {
    const { query, format = "json", depth = 3, max_pages = 100, timeout = 300 } = args;

    try {
      // Build command arguments
      const cmdArgs = [
        query,
        "--format",
        format,
        "--depth",
        depth.toString(),
        "--max-pages",
        max_pages.toString(),
        "--timeout",
        timeout.toString(),
      ];

      // Spawn subprocess to run werdeep CLI
      const result = await spawnProcess("werdeep", cmdArgs);

      // Parse JSON output
      const output: WeRDeepResult = JSON.parse(result);

      if (output.status === "error") {
        return JSON.stringify({
          success: false,
          error: output.error,
        });
      }

      return JSON.stringify({
        success: true,
        data: output,
      });
    } catch (error) {
      // Handle subprocess errors
      return JSON.stringify({
        success: false,
        error: {
          code: "INTERNAL_ERROR",
          message: error instanceof Error ? error.message : "Unknown error occurred",
          action: "Please try again or contact support",
        },
      });
    }
  },
};

/**
 * Spawn a subprocess and capture output
 */
async function spawnProcess(command: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const { spawn } = require("child_process");
    const process = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    process.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    process.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    process.on("close", (code: number) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(`Process exited with code ${code}: ${stderr}`));
      }
    });

    process.on("error", (error: Error) => {
      reject(error);
    });
  });
}

export default werdeepTool;
