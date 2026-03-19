export type OfferResponse = {
  id: string;
  productId: string;
  provider: string;
  price: number;
  currency: string;
  url: string;
  availability: boolean;
  lastSeenAt: string;
  createdAt: string;
};
