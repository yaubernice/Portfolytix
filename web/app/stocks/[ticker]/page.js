import { redirect } from "next/navigation";

export default async function StockPage({ params }) {
  const { ticker } = await params;
  redirect(`/securities/${encodeURIComponent(ticker)}`);
}
