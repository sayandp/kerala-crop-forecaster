import { ogContentType, ogImage, ogSize } from "@/lib/og";
import { langStaticParams } from "@/lib/page";

export const size = ogSize;
export const contentType = ogContentType;
export const generateStaticParams = langStaticParams;
export const alt = "Data drift";

export default function Image() {
  return ogImage("Data drift", "Weekly Evidently check of model inputs");
}
