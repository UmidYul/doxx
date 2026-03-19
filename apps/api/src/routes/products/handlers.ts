import { NextResponse } from "next/server";

import { db } from "@/lib/db";
import { error as logError } from "@/lib/logger";
import type { OfferResponse } from "@/dto/offer.dto";
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

function toOfferResponse(o: {
  id: string;
  productId: string;
  provider: string;
  price: number;
  currency: string;
  url: string;
  availability: boolean;
  lastSeenAt: Date;
  createdAt: Date;
}): OfferResponse {
  return {
    id: o.id,
    productId: o.productId,
    provider: o.provider,
    price: o.price,
    currency: o.currency,
    url: o.url,
    availability: o.availability,
    lastSeenAt: o.lastSeenAt.toISOString(),
    createdAt: o.createdAt.toISOString(),
  };
}

export async function getProducts(request: Request): Promise<NextResponse> {
  try {
    const url = new URL(request.url);

    const pageRaw = url.searchParams.get("page");
    const limitRaw = url.searchParams.get("limit");

    const pageNum = pageRaw ? Number(pageRaw) : 1;
    const limitNum = limitRaw ? Number(limitRaw) : 20;

    if (!Number.isFinite(pageNum) || pageNum < 1 || !Number.isFinite(limitNum) || limitNum < 1) {
      return NextResponse.json({ error: "Invalid query params" }, { status: 400 });
    }

    const limit = Math.floor(limitNum);
    if (limit > 50) {
      return NextResponse.json({ error: "Invalid query params" }, { status: 400 });
    }
    const page = Math.floor(pageNum);

    const skip = (page - 1) * limit;

    const products = await db.product.findMany({
      orderBy: { createdAt: "desc" },
      skip,
      take: limit,
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

    return NextResponse.json({
      items: products.map(toProductResponse),
      page,
      limit,
    });
  } catch (e) {
    logError("getProducts failed", { error: e instanceof Error ? e.message : e });
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

export async function getProductById(
  _request: Request,
  params: { id: string },
): Promise<NextResponse> {
  try {
    const product = await db.product.findUnique({
      where: { id: params.id },
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

    if (!product) {
      return NextResponse.json({ error: "Not Found" }, { status: 404 });
    }

    return NextResponse.json(toProductResponse(product));
  } catch (e) {
    logError("getProductById failed", { id: params.id, error: e instanceof Error ? e.message : e });
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

export async function getProductOffers(
  _request: Request,
  params: { id: string },
): Promise<NextResponse> {
  try {
    const offers = await db.offer.findMany({
      where: { productId: params.id },
      orderBy: { price: "asc" },
      select: {
        id: true,
        productId: true,
        provider: true,
        price: true,
        currency: true,
        url: true,
        availability: true,
        lastSeenAt: true,
        createdAt: true,
      },
    });

    return NextResponse.json({
      items: offers.map(toOfferResponse),
    });
  } catch (e) {
    logError("getProductOffers failed", { id: params.id, error: e instanceof Error ? e.message : e });
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
