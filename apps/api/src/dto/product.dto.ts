export type ProductResponse = {
  id: string;
  title: string;
  brand: string | null;
  model: string | null;
  categoryId: string | null;
  attributes: unknown | null;
  createdAt: string;
  updatedAt: string;
};
