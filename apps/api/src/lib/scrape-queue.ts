import { Queue } from "bullmq";

import { error, info } from "@/lib/logger";

const connection = { url: process.env.REDIS_URL ?? "redis://localhost:6379" };

const queue = new Queue("scrape", { connection });

export async function addScrapeJob(url: string) {
  try {
    await queue.add(
      "scrape",
      { url },
      {
        attempts: 3,
        backoff: { type: "exponential", delay: 1000 },
      },
    );
    info("Scrape job queued", { url });
  } catch (e) {
    error("addScrapeJob failed", { url, error: e instanceof Error ? e.message : e });
    throw e;
  }
}
