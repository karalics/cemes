/*
 * Behaviour for the htmx admin that is more than a declarative
 * attribute can express. Alpine covers the small local state - open
 * panels, toggles - and htmx covers everything that is a request.
 * What's left is here:
 *
 *   - the change list's select-all checkbox and selection counter
 *   - adding, removing and reordering inline formset rows, replacing
 *     Mezzanine's jQuery dynamic_inline.js
 *   - drag and drop in the page tree, replacing nestedSortable, posting
 *     to the same ordering endpoint the classic admin uses
 *
 * All listeners are delegated from the document, so regions swapped in
 * by htmx keep working without re-initialisation.
 */
(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  /* ------------------------------------------------------------------ */
  /* Change list selection                                              */
  /* ------------------------------------------------------------------ */

  function updateCounter(scope) {
    var counter = scope.querySelector("[data-action-counter]");
    if (!counter) {
      return;
    }
    var checked = scope.querySelectorAll(".action-select:checked").length;
    counter.textContent = checked
      ? checked + " " + counter.dataset.labelSelected
      : "";
  }

  document.addEventListener("change", function (event) {
    var target = event.target;
    var main = target.closest(".cl-main");
    if (!main) {
      return;
    }
    if (target.matches("[data-select-all]")) {
      main.querySelectorAll(".action-select").forEach(function (box) {
        box.checked = target.checked;
      });
      updateCounter(main);
    } else if (target.matches(".action-select")) {
      var all = main.querySelector("[data-select-all]");
      if (all) {
        var boxes = main.querySelectorAll(".action-select");
        var checked = main.querySelectorAll(".action-select:checked");
        all.checked = boxes.length === checked.length;
      }
      updateCounter(main);
    }
  });

  /* ------------------------------------------------------------------ */
  /* Inline formsets                                                    */
  /* ------------------------------------------------------------------ */

  function totalFormsInput(group) {
    return document.querySelector(
      '[name="' + group.dataset.inlinePrefix + '-TOTAL_FORMS"]'
    );
  }

  function liveRows(group) {
    return Array.prototype.filter.call(
      group.querySelectorAll(".inline-row"),
      function (row) {
        return !row.hasAttribute("data-inline-template");
      }
    );
  }

  /*
   * Rewrite the formset index embedded in a row's field names and ids,
   * eg "fields-2-label" becomes "fields-5-label".
   *
   * aria-describedby and aria-labelledby are rewritten too: Django
   * renders them pointing at the id of a field's help text, so leaving
   * them behind would silently break the association for screen
   * readers in every row that gets added or renumbered.
   */
  var INDEXED_ATTRS = ["name", "id", "for", "aria-describedby", "aria-labelledby"];

  function setRowIndex(row, prefix, index) {
    var pattern = new RegExp(prefix + "-(?:__prefix__|\\d+)", "g");
    var replacement = prefix + "-" + index;
    var selector = INDEXED_ATTRS.map(function (attr) {
      return "[" + attr + "]";
    }).join(", ");
    row.querySelectorAll(selector).forEach(function (el) {
      INDEXED_ATTRS.forEach(function (attr) {
        var value = el.getAttribute(attr);
        if (value) {
          el.setAttribute(attr, value.replace(pattern, replacement));
        }
      });
    });
  }

  /*
   * Orderable models carry an "_order" field whose widget is hidden;
   * its value is the row's position.
   */
  function renumberOrder(group) {
    liveRows(group).forEach(function (row, index) {
      var order = row.querySelector('input[name$="-_order"]');
      if (order) {
        order.value = index;
      }
    });
  }

  function reindex(group) {
    var prefix = group.dataset.inlinePrefix;
    liveRows(group).forEach(function (row, index) {
      setRowIndex(row, prefix, index);
    });
    renumberOrder(group);
  }

  function addRow(group) {
    var template = group.querySelector("[data-inline-template]");
    var total = totalFormsInput(group);
    if (!template || !total) {
      return;
    }
    var maxNum = parseInt(group.dataset.maxNum, 10);
    if (!isNaN(maxNum) && liveRows(group).length >= maxNum) {
      return;
    }
    var row = template.cloneNode(true);
    row.removeAttribute("hidden");
    row.removeAttribute("data-inline-template");
    row.classList.remove("empty-form");
    setRowIndex(row, group.dataset.inlinePrefix, parseInt(total.value, 10));
    template.parentNode.insertBefore(row, template);
    total.value = parseInt(total.value, 10) + 1;
    renumberOrder(group);
    var first = row.querySelector("input:not([type=hidden]), select, textarea");
    if (first) {
      first.focus();
    }
  }

  function deleteRow(group, row) {
    var flag = row.querySelector('input[name$="-DELETE"]');
    var pk = row.querySelector('input[name$="-id"]');
    if (pk && pk.value) {
      // Saved object: mark it for deletion and let the formset do it.
      if (flag) {
        flag.checked = true;
      }
      row.classList.add("marked-deleted");
      row.setAttribute("aria-hidden", "true");
      return;
    }
    // Unsaved row: drop it and close the gap in the formset indexes.
    var total = totalFormsInput(group);
    row.parentNode.removeChild(row);
    if (total) {
      total.value = Math.max(0, parseInt(total.value, 10) - 1);
    }
    reindex(group);
  }

  function moveRow(group, row, direction) {
    var rows = liveRows(group);
    var index = rows.indexOf(row);
    var swapWith = direction === "up" ? rows[index - 1] : rows[index + 1];
    if (!swapWith) {
      return;
    }
    if (direction === "up") {
      row.parentNode.insertBefore(row, swapWith);
    } else {
      row.parentNode.insertBefore(swapWith, row);
    }
    renumberOrder(group);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(
      "[data-add-row], [data-row-delete], .row-move"
    );
    if (!button) {
      return;
    }
    var group = button.closest(".inline-group");
    if (!group) {
      return;
    }
    event.preventDefault();
    if (button.hasAttribute("data-add-row")) {
      addRow(group);
    } else if (button.hasAttribute("data-row-delete")) {
      deleteRow(group, button.closest(".inline-row"));
    } else {
      moveRow(group, button.closest(".inline-row"), button.dataset.move);
    }
  });

  /* ------------------------------------------------------------------ */
  /* Page tree                                                          */
  /* ------------------------------------------------------------------ */

  var dragged = null;

  document.addEventListener("dragstart", function (event) {
    var node = event.target.closest(".tree-node");
    if (!node || !node.closest("[data-page-tree]")) {
      return;
    }
    dragged = node;
    node.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    // Firefox requires data to be set for a drag to start at all.
    event.dataTransfer.setData("text/plain", node.dataset.pageId);
  });

  document.addEventListener("dragend", function () {
    if (dragged) {
      dragged.classList.remove("dragging");
    }
    document.querySelectorAll(".drop-before, .drop-after, .drop-into")
      .forEach(function (el) {
        el.classList.remove("drop-before", "drop-after", "drop-into");
      });
    dragged = null;
  });

  /*
   * Where a drop would land: the upper or lower half of a row makes the
   * dragged page a sibling before or after it, and dragging further to
   * the right nests it as a child.
   */
  function dropIntent(row, event) {
    var box = row.getBoundingClientRect();
    if (event.clientX - box.left > 56) {
      return "into";
    }
    return event.clientY - box.top < box.height / 2 ? "before" : "after";
  }

  document.addEventListener("dragover", function (event) {
    if (!dragged) {
      return;
    }
    var row = event.target.closest(".tree-row");
    if (!row || !row.closest("[data-page-tree]")) {
      return;
    }
    var node = row.closest(".tree-node");
    if (node === dragged || dragged.contains(node)) {
      return;
    }
    event.preventDefault();
    var intent = dropIntent(row, event);
    row.classList.remove("drop-before", "drop-after", "drop-into");
    row.classList.add("drop-" + intent);
  });

  document.addEventListener("dragleave", function (event) {
    var row = event.target.closest(".tree-row");
    if (row) {
      row.classList.remove("drop-before", "drop-after", "drop-into");
    }
  });

  document.addEventListener("drop", function (event) {
    if (!dragged) {
      return;
    }
    var row = event.target.closest(".tree-row");
    if (!row || !row.closest("[data-page-tree]")) {
      return;
    }
    var target = row.closest(".tree-node");
    if (target === dragged || dragged.contains(target)) {
      return;
    }
    event.preventDefault();
    var intent = dropIntent(row, event);

    if (intent === "into") {
      var branch = target.querySelector(":scope > .tree-branch");
      if (!branch) {
        branch = document.createElement("ul");
        branch.className = "tree-branch";
        target.appendChild(branch);
      }
      branch.appendChild(dragged);
    } else if (intent === "before") {
      target.parentNode.insertBefore(dragged, target);
    } else {
      target.parentNode.insertBefore(dragged, target.nextSibling);
    }
    persistTree(dragged);
  });

  function persistTree(node) {
    var tree = node.closest("[data-page-tree]");
    var parentNode = node.parentNode.closest(".tree-node");
    var siblings = Array.prototype.map.call(
      node.parentNode.children,
      function (child) {
        return child.dataset.pageId;
      }
    );

    var body = new FormData();
    body.append("id", node.dataset.pageId);
    body.append("parent_id", parentNode ? parentNode.dataset.pageId : "");
    siblings.forEach(function (id) {
      body.append("siblings[]", id);
    });

    fetch(tree.dataset.orderingUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
      body: body,
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.ok ? response.text() : "error";
      })
      .then(function (text) {
        // The ordering view refuses moves that break a page's own
        // can_move() rules, and reports why through the messages
        // framework - so reload to surface it.
        if (text.trim() !== "ok") {
          window.location.reload();
        }
      })
      .catch(function () {
        window.location.reload();
      });
  }

  /* ------------------------------------------------------------------ */
  /* Unsaved changes guard                                              */
  /* ------------------------------------------------------------------ */

  var formDirty = false;
  document.addEventListener("input", function (event) {
    if (event.target.closest("[data-change-form]")) {
      formDirty = true;
    }
  });
  document.addEventListener("submit", function () {
    formDirty = false;
  });
  window.addEventListener("beforeunload", function (event) {
    if (formDirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
