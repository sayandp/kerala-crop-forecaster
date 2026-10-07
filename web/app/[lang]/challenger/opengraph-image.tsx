import { ogContentType, ogImage, ogSize } from "@/lib/og";
import { langStaticParams } from "@/lib/page";

export const size = ogSize;
export const contentType = ogContentType;
export const generateStaticParams = langStaticParams;
export const alt = "The shadow challenger";

export default function Image() {
  return ogImage("The shadow challenger", "A pre-registered test on new data only");
}
