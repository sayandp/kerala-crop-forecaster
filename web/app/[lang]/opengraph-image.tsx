import { ogContentType, ogImage, ogSize } from "@/lib/og";
import { langStaticParams } from "@/lib/page";

export const size = ogSize;
export const contentType = ogContentType;
export const generateStaticParams = langStaticParams;
export const alt = "Kerala crop prices";

export default function Image() {
  return ogImage("Kerala crop prices", "Today's mandi price and the expected range in 7 days");
}
