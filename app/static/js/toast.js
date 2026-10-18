(function () {
  const toastElement = document.getElementById("toast");
  const toastBody = document.getElementById("toast-body");
  // The markup says the same thing; passing it here keeps the behaviour if the
  // element is ever rebuilt without its data attribute.
  const toast = new bootstrap.Toast(toastElement, { autohide: false });

  htmx.on("showMessage", (e) => {
    toastBody.innerText = e.detail.value;
    toast.show();
  });
})();
