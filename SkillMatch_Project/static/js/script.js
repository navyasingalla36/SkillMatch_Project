// Fade out flash messages after 5 seconds
document.querySelectorAll('.alert').forEach(function (el) {
    setTimeout(function () {
        el.style.opacity = '0';
        setTimeout(function () { el.remove(); }, 400);
    }, 5000);
});

// Ask for confirmation before submitting forms marked with data-confirm
document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
        if (!confirm(form.dataset.confirm)) { e.preventDefault(); }
    });
});
