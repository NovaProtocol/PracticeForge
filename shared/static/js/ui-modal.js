/* The app's modal system, replacing Bootstrap's. `.ui-modal` is the overlay and
   `.is-open` reveals it; openers/closers are data attributes so the templates
   carry no inline handlers. A modal marked `data-backdrop="static"` (the solver
   run dialog) ignores backdrop clicks and Escape. */
(function () {
  function openModal(target) {
    var modal = typeof target === "string" ? document.querySelector(target) : target;
    if (!modal) return;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeModal(target) {
    var modal = typeof target === "string" ? document.querySelector(target) : target;
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    if (!document.querySelector(".ui-modal.is-open")) document.body.style.overflow = "";
  }

  document.addEventListener("click", function (ev) {
    var opener = ev.target.closest("[data-modal-open]");
    if (opener) {
      ev.preventDefault();
      openModal(opener.getAttribute("data-modal-open"));
      return;
    }
    var closer = ev.target.closest("[data-modal-close]");
    if (closer) {
      ev.preventDefault();
      closeModal(closer.closest(".ui-modal"));
      return;
    }
    if (
      ev.target.classList &&
      ev.target.classList.contains("ui-modal") &&
      ev.target.getAttribute("data-backdrop") !== "static"
    ) {
      closeModal(ev.target);
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var open = document.querySelector(".ui-modal.is-open");
    if (open && open.getAttribute("data-backdrop") !== "static") closeModal(open);
  });

  window.openModal = openModal;
  window.closeModal = closeModal;
})();
