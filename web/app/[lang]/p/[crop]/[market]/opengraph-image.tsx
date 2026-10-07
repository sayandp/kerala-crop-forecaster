import { ogContentType, ogImage, ogSize } from "@/lib/og";

export const size = ogSize;
export const contentType = ogContentType;
export const alt = "Kerala crop prices";

export default function Image() {
  return ogImage("Kerala crop prices", "Price history and the expected range");
}
