/* ============================================================
   账簿 · 个人收支记账  界面交互层
   职责：服务端消息转提示条、录入表单校验、类别联动、
        删除二次确认、筛选条件自检。
   只依赖原生 JS，不引入任何框架。
   ============================================================ */
(function () {
  'use strict';

  /* ---------------- 提示条 ---------------- */
  var stack = document.getElementById('toastStack');

  function toast(message, type) {
    if (!stack || !message) return;
    var el = document.createElement('div');
    el.className = 'toast' + (type === 'error' ? ' is-error' : type === 'success' ? ' is-success' : '');
    el.textContent = message;
    stack.appendChild(el);

    setTimeout(function () {
      el.classList.add('is-out');
      setTimeout(function () { el.remove(); }, 220);
    }, type === 'error' ? 3600 : 2400);
  }
  window.showToast = toast;

  //  Flask flash 消息 -> 提示条
  var flashBox = document.getElementById('flash-data');
  if (flashBox) {
    var messages = [];
    try { messages = JSON.parse(flashBox.textContent) || []; } catch (err) { messages = []; }
    messages.forEach(function (pair, i) {
      var category = pair[0];
      var text = pair[1];
      setTimeout(function () {
        toast(text, category === 'error' ? 'error' : category === 'success' ? 'success' : 'info');
      }, i * 180);
    });
  }

  /* ---------------- 确认弹窗 ---------------- */
  var activeDialog = null;

  function closeDialog() {
    if (!activeDialog) return;
    activeDialog.remove();
    activeDialog = null;
    document.removeEventListener('keydown', onDialogKey);
  }

  function onDialogKey(e) {
    if (e.key === 'Escape') closeDialog();
  }

  function openConfirm(text, onOk, okLabel) {
    closeDialog();

    var overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');

    var box = document.createElement('div');
    box.className = 'dialog';

    var title = document.createElement('p');
    title.className = 'dialog-title';
    title.textContent = '确认操作';

    var body = document.createElement('p');
    body.className = 'dialog-body';
    body.textContent = text;

    var actions = document.createElement('div');
    actions.className = 'dialog-actions';

    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn btn-ghost';
    cancel.textContent = '取消';

    var ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'btn btn-danger';
    ok.textContent = okLabel || '确认删除';

    actions.appendChild(cancel);
    actions.appendChild(ok);
    box.appendChild(title);
    box.appendChild(body);
    box.appendChild(actions);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    activeDialog = overlay;

    cancel.addEventListener('click', closeDialog);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeDialog();
    });
    ok.addEventListener('click', function () {
      closeDialog();
      onOk();
    });
    document.addEventListener('keydown', onDialogKey);
    ok.focus();
  }

  /* ---------------- 表单校验 ---------------- */
  var AMOUNT_RE = /^\d+(\.\d{1,2})?$/;

  function fieldOf(input) {
    return input.closest('.field');
  }

  function showError(input, message) {
    var field = fieldOf(input);
    if (!field) { toast(message, 'error'); return; }
    var slot = field.querySelector('[data-err-for="' + input.dataset.rule + '"]');
    input.setAttribute('aria-invalid', 'true');
    if (slot) {
      slot.textContent = message;
      slot.hidden = false;
    } else {
      toast(message, 'error');
    }
  }

  function clearError(input) {
    var field = fieldOf(input);
    input.removeAttribute('aria-invalid');
    if (!field) return;
    var slot = field.querySelector('[data-err-for="' + input.dataset.rule + '"]');
    if (slot) { slot.textContent = ''; slot.hidden = true; }
  }

  function validate(input) {
    var rule = input.dataset.rule;
    var value = (input.value || '').trim();

    if (rule === 'amount') {
      if (!value) return showError(input, '金额不能为空'), false;
      if (!AMOUNT_RE.test(value)) return showError(input, '只能填数字，最多两位小数'), false;
      if (parseFloat(value) <= 0) return showError(input, '金额要大于 0'), false;
      if (parseFloat(value) > 10000000) return showError(input, '金额看起来太大了，请核对'), false;
      clearError(input);
      return true;
    }

    if (rule === 'date') {
      if (!value) return showError(input, '请选择日期'), false;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return showError(input, '日期格式不对'), false;
      clearError(input);
      return true;
    }

    if (rule === 'category') {
      if (!value) return showError(input, '请选择类别'), false;
      clearError(input);
      return true;
    }
    return true;
  }

  document.querySelectorAll('[data-entry-form], [data-cat-form]').forEach(function (form) {
    var fields = Array.prototype.slice.call(form.querySelectorAll('[data-rule]'));

    fields.forEach(function (input) {
      input.addEventListener('blur', function () {
        if ((input.value || '').trim()) validate(input);
      });
      input.addEventListener('input', function () {
        if (input.getAttribute('aria-invalid') === 'true') validate(input);
      });
    });

    form.addEventListener('submit', function (e) {
      var ok = true;
      var firstBad = null;
      fields.forEach(function (input) {
        if (!validate(input) && ok) {
          ok = false;
          firstBad = input;
        }
      });

      if (!ok) {
        e.preventDefault();
        if (firstBad) firstBad.focus();
        toast('还有必填项没填好', 'error');
        return;
      }

      var btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.classList.add('is-busy');
        var label = btn.querySelector('.btn-label');
        if (label) label.textContent = '正在记上…';
      }
    });
  });

  /* ---------------- 收支类型 -> 类别联动 ---------------- */
  document.querySelectorAll('[data-category-select]').forEach(function (select) {
    var form = select.closest('form');
    if (!form) return;
    var radios = form.querySelectorAll('input[name="type"]');

    function sync() {
      var checked = form.querySelector('input[name="type"]:checked');
      var type = checked ? checked.value : 'expense';
      var firstUsable = null;

      Array.prototype.forEach.call(select.options, function (option) {
        var usable = !option.dataset.type || option.dataset.type === type;
        option.hidden = !usable;
        option.disabled = !usable;
        if (usable && !firstUsable) firstUsable = option;
      });

      var current = select.options[select.selectedIndex];
      if (!current || current.disabled) {
        if (firstUsable) select.value = firstUsable.value;
      }
    }

    radios.forEach(function (r) { r.addEventListener('change', sync); });
    sync();
  });

  /* ---------------- 删除等危险操作二次确认 ---------------- */
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.confirmed === '1') return;
      e.preventDefault();
      openConfirm(form.dataset.confirm, function () {
        form.dataset.confirmed = '1';
        form.submit();
      }, form.dataset.confirmLabel || '确认删除');
    });
  });

  /* ---------------- 筛选条件自检 ---------------- */
  var filterForm = document.querySelector('[data-filter-form]');
  if (filterForm) {
    filterForm.addEventListener('submit', function (e) {
      var start = filterForm.querySelector('input[name="start"]');
      var end = filterForm.querySelector('input[name="end"]');
      if (start && end && start.value && end.value && start.value > end.value) {
        e.preventDefault();
        toast('起始日期晚于结束日期，换个范围试试', 'error');
        end.focus();
      }
    });
  }

  /* ---------------- 类别新增表单：空名拦截 ---------------- */
  document.querySelectorAll('[data-cat-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      var name = form.querySelector('input[name="name"]');
      if (!name) return;
      if (!name.value.trim()) {
        e.preventDefault();
        toast('类别名称不能为空', 'error');
        name.focus();
      }
    });
  });

  /* ---------------- 日期框：空值时隐藏浏览器占位符 ---------------- */
  function refreshDateFields() {
    document.querySelectorAll('input[type="date"]').forEach(function (input) {
      input.classList.toggle('has-value', input.value !== '');
    });
  }
  document.querySelectorAll('input[type="date"]').forEach(function (input) {
    input.addEventListener('input', refreshDateFields);
    input.addEventListener('change', refreshDateFields);
  });
  refreshDateFields();
})();
