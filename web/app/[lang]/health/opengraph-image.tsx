import { ogContentType, ogImage, ogSize } from "@/lib/og";
import { langStaticParams } from "@/lib/page";

export const size = ogSize;
export const contentType = ogContentType;
export const generateStaticParams = langStaticParams;
export const alt = "System health";

export default function Image() {
  return ogImage("System health", "Daily pipeline runs, database size, subscribers");
}
