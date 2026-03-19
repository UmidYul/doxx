import { NextResponse } from "next/server";

import { db } from "@/lib/db";
import { error as logError } from "@/lib/logger";
import type { ProductResponse } from "@/dto/product.dto";

function toProductResponse(p: {
  id: string;
  title: string;
  brand: string | null;
  model: string | null;
  categoryId: string | null;
  attributes: unknown | null;
  createdAt: Date;
  updatedAt: Date;
}): ProductResponse {
  return {
    id: p.id,
    title: p.title,
    brand: p.brand,
    model: p.model,
    categoryId: p.categoryId,
    attributes: p.attributes,
    createdAt: p.createdAt.toISOString(),
    updatedAt: p.updatedAt.toISOString(),
  };
}

export async function searchProducts(request: Request): Promise<NextResponse> {
  try {
    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").trim();

    if (!q) {
      return NextResponse.json({ items: [] });
    }

    if (q.length > 200) {
      return NextResponse.json({ error: "Invalid query params" }, { status: 400 });
    }

    const products = await db.product.findMany({
      where: {
        title: {
          contains: q,
          mode: "insensitive",
        },
      },
      orderBy: { createdAt: "desc" },
      take: 20,
      select: {
        id: true,
        title: true,
        brand: true,
        model: true,
        categoryId: true,
        attributes: true,
        createdAt: true,
        updatedAt: true,
      },
    });

    return NextResponse.json({ items: products.map(toProductResponse) });
  } catch (e) {
    logError("searchProducts failed", { error: e instanceof Error ? e.message : e });
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
