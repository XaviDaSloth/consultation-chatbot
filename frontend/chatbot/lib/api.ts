const DEFAULT_API_PORT = "8000";

export function getApiUrl(path = "") {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;

  if (typeof window === "undefined") {
    return `${configuredUrl ?? `http://127.0.0.1:${DEFAULT_API_PORT}`}${path}`;
  }

  const fallbackUrl = `http://${window.location.hostname}:${DEFAULT_API_PORT}`;

  if (!configuredUrl) {
    return `${fallbackUrl}${path}`;
  }

  try {
    const url = new URL(configuredUrl);
    const isLoopback = url.hostname === "127.0.0.1" || url.hostname === "localhost";

    if (isLoopback && window.location.hostname !== "localhost") {
      url.hostname = window.location.hostname;
    }

    return `${url.origin}${path}`;
  } catch {
    return `${fallbackUrl}${path}`;
  }
}
