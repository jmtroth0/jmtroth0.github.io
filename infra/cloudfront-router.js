// CloudFront Function (viewer request) for the personal site.
//
//   jordanroth.xyz/*            -> 301 https://www.jordanroth.xyz/*
//   portfolio.jordanroth.xyz/   -> serves /photos/index.html (the gallery)
//   portfolio.jordanroth.xyz/*  -> shared files pass through; any other page 301s to www
//   www.jordanroth.xyz/photos/  -> 301 https://portfolio.jordanroth.xyz/
//   */folder/                   -> serves */folder/index.html
//   */folder                    -> 301 */folder/
//
// On the *.cloudfront.net test address, /photos/ is served directly so the gallery
// can be checked before the domains move.

var WWW = "https://www.jordanroth.xyz";
var PORTFOLIO = "https://portfolio.jordanroth.xyz";

function redirect(location) {
  return {
    statusCode: 301,
    statusDescription: "Moved Permanently",
    headers: { location: { value: location } },
  };
}

function isSharedFile(uri) {
  return uri.indexOf("/_astro/") === 0 || uri === "/favicon.ico" || uri === "/apple-touch-icon.png" || uri === "/404.html";
}

function handler(event) {
  var request = event.request;
  var host = request.headers.host ? request.headers.host.value : "";
  var uri = request.uri;

  if (host === "jordanroth.xyz") {
    return redirect(WWW + uri);
  }

  if (host === "portfolio.jordanroth.xyz") {
    if (uri === "/" || uri === "/index.html") {
      request.uri = "/photos/index.html";
      return request;
    }
    if (isSharedFile(uri)) {
      return request;
    }
    return redirect(WWW + uri);
  }

  var testing = host.slice(-15) === ".cloudfront.net";
  if (!testing && (uri === "/photos" || uri === "/photos/" || uri === "/photos/index.html")) {
    return redirect(PORTFOLIO + "/");
  }

  if (uri.slice(-1) === "/") {
    request.uri = uri + "index.html";
  } else if (uri.split("/").pop().indexOf(".") === -1) {
    return redirect(uri + "/");
  }
  return request;
}
