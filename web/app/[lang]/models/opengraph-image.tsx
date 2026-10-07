import { ogContentType, ogImage, ogSize } from "@/lib/og";
import { langStaticParams } from "@/lib/page";

export const size = ogSize;
export const contentType = ogContentType;
export const generateStaticParams = langStaticParams;
export const alt = "Models and decisions";

export default function Image() {
  return ogImage("Models and decisions", "Every promotion decision, with its evidence");
}
