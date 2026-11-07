(function () {
  'use strict';

  function dismissFlash(element) {
    if (!element || !element.parentNode) return;
    element.classList.add('is-hiding');
    window.setTimeout(function () {
      if (element.parentNode) element.parentNode.removeChild(element);
    }, 200);
  }

  function ensureFlashStack() {
    var stack = document.querySelector('.flash-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'flash-stack';
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    return stack;
  }

  function showToast(message, type) {
    var stack = ensureFlashStack();
    var toast = document.createElement('div');
    toast.className = 'flash flash-' + (type || 'success');
    toast.setAttribute('role', 'status');

    var text = document.createElement('span');
    text.textContent = message;

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'flash-close';
    close.setAttribute('aria-label', '关闭');
    close.innerHTML = '&times;';
    close.addEventListener('click', function () {
      dismissFlash(toast);
    });

    toast.appendChild(text);
    toast.appendChild(close);
    stack.appendChild(toast);

    window.setTimeout(function () {
      dismissFlash(toast);
    }, 4000);
  }

  window.showToast = showToast;

  document.querySelectorAll('.flash').forEach(function (flash) {
    window.setTimeout(function () {
      dismissFlash(flash);
    }, 4000);

    var close = flash.querySelector('[data-dismiss]');
    if (close) {
      close.addEventListener('click', function () {
        dismissFlash(flash);
      });
    }
  });

  var navToggle = document.querySelector('[data-nav-toggle]');
  var nav = document.querySelector('[data-nav]');

  if (navToggle && nav) {
    navToggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      navToggle.classList.toggle('is-open', open);
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    nav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        nav.classList.remove('is-open');
        navToggle.classList.remove('is-open');
        navToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  var modal = document.querySelector('#confirm-modal');
  var pendingForm = null;

  if (modal) {
    var modalMessage = modal.querySelector('#confirm-message');
    var confirmButton = modal.querySelector('[data-modal-confirm]');
    var cancelButton = modal.querySelector('[data-modal-cancel]');

    var closeModal = function () {
      modal.hidden = true;
      document.body.classList.remove('modal-open');
      pendingForm = null;
    };

    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (form.dataset.confirmed === 'true') return;
        event.preventDefault();
        pendingForm = form;
        if (modalMessage) {
          modalMessage.textContent = form.dataset.confirm || '确定要删除吗？该操作不可撤销。';
        }
        modal.hidden = false;
        document.body.classList.add('modal-open');
        if (confirmButton) confirmButton.focus();
      });
    });

    if (cancelButton) {
      cancelButton.addEventListener('click', closeModal);
    }

    if (confirmButton) {
      confirmButton.addEventListener('click', function () {
        var form = pendingForm;
        closeModal();
        if (form) {
          form.dataset.confirmed = 'true';
          form.submit();
        }
      });
    }

    modal.addEventListener('click', function (event) {
      if (event.target === modal) closeModal();
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !modal.hidden) closeModal();
    });
  }

  document.querySelectorAll('[data-segmented]').forEach(function (group) {
    var inputs = group.querySelectorAll('input[type="radio"]');
    inputs.forEach(function (input) {
      input.addEventListener('change', function () {
        group.querySelectorAll('.segment').forEach(function (segment) {
          segment.classList.toggle('is-active', segment.contains(input) && input.checked);
        });
      });
    });
  });

  function updateCategorySelects(form) {
    var checked = form.querySelector('input[name="type"]:checked');
    var type = checked ? checked.value : 'expense';

    form.querySelectorAll('[data-category-type]').forEach(function (select) {
      var isActive = select.dataset.categoryType === type;
      select.disabled = !isActive;
      select.hidden = !isActive;
      select.required = isActive && select.dataset.required === 'true';
    });
  }

  function setError(form, name, message) {
    var error = form.querySelector('[data-error-for="' + name + '"]');
    if (!error) return;
    error.textContent = message;
    var field = error.closest('.field');
    if (field) field.classList.add('has-error');
  }

  function clearErrors(form) {
    form.querySelectorAll('.field-error').forEach(function (error) {
      error.textContent = '';
    });
    form.querySelectorAll('.field').forEach(function (field) {
      field.classList.remove('has-error');
    });
  }

  function focusFirstError(form) {
    var field = form.querySelector('.field.has-error');
    if (!field) return;
    var input = field.querySelector(
      'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled])'
    );
    if (input) input.focus();
  }

  document.querySelectorAll('form[data-validate]').forEach(function (form) {
    form.noValidate = true;

    form.querySelectorAll('input[name="type"]').forEach(function (radio) {
      radio.addEventListener('change', function () {
        updateCategorySelects(form);
      });
    });

    updateCategorySelects(form);

    form.addEventListener('submit', function (event) {
      var valid = true;
      clearErrors(form);

      var dateField = form.querySelector('input[name="date"]');
      if (dateField && !dateField.value) {
        setError(form, 'date', '请选择日期');
        valid = false;
      }

      var amountField = form.querySelector('input[name="amount"]');
      if (amountField) {
        var amount = parseFloat(amountField.value);
        if (!amountField.value || !isFinite(amount) || amount <= 0) {
          setError(form, 'amount', '请输入大于 0 的金额');
          valid = false;
        }
      }

      var activeCategory = form.querySelector('[data-category-type]:not([disabled])');
      if (activeCategory && !activeCategory.value) {
        setError(form, 'category', '请选择类别');
        valid = false;
      }

      var nameField = form.querySelector('input[name="name"]');
      if (nameField && !nameField.value.trim()) {
        setError(form, 'name', '请输入类别名称');
        valid = false;
      }

      if (!valid) {
        event.preventDefault();
        focusFirstError(form);
      }
    });
  });
})();
