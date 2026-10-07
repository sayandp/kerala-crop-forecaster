import { ogContentType, ogImage, ogSize } from "@/lib/og";
import { langStaticParams } from "@/lib/page";

export const size = ogSize;
export const contentType = ogContentType;
export const generateStaticParams = langStaticParams;
export const alt = "How accurate is it?";

export default function Image() {
  return ogImage("How accurate is it?", "Live error vs the naive last-price forecast");
}
