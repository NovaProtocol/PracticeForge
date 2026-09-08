(function () {
  "use strict";
  function detail(err, ctx) {
    var payload = {
      message: err && err.message ? err.message : String(err),
      stack: err && err.stack ? err.stack : null,
      url: ctx && ctx.url ? ctx.url : location.href,
      method: ctx && ctx.method ? ctx.method : null,
      status: ctx && ctx.status ? ctx.status : null,
      request_id: ctx && ctx.request_id ? ctx.request_id : null,
      body: ctx && ctx.body ? ctx.body : null,
      timestamp: new Date().toISOString(),
    };
    try { console.error(payload); } catch (e) { console.error(err); }
    try {
      var msg = payload.message + (payload.request_id ? " [" + payload.request_id + "]" : "");
      if (window.showToast) window.showToast(msg, "error");
      else if (window.toastr) window.toastr.error(msg);
    } catch (e2) {}
    return payload;
  }
  window.addEventListener("error", function (e) {
    detail(e.error || e.message, { url: location.href });
  });
  window.addEventListener("unhandledrejection", function (e) {
    detail(e.reason, { url: location.href });
  });
  window.apiFetch = async function (url, opts) {
    opts = opts || {};
    try {
      var resp = await fetch(url, opts);
      if (!resp.ok) {
        var rid = resp.headers.get("X-Request-ID") || "";
        var body = null;
        try { body = await resp.clone().json(); } catch (e) { try { body = await resp.clone().text(); } catch (ee) {} }
        detail(new Error("apiFetch " + (opts.method || "GET") + " " + url + " -> " + resp.status), {
          url: url, method: opts.method || "GET", status: resp.status, request_id: rid, body: body,
        });
        var err = new Error(body && body.error && body.error.message ? body.error.message : "Request failed (" + resp.status + ")");
        err.status = resp.status; err.request_id = rid; err.body = body;
        throw err;
      }
      return resp;
    } catch (err) {
      if (!err.status) detail(err, { url: url, method: opts.method || "GET" });
      throw err;
    }
  };
})();
