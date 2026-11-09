/*
 * Django loads jQuery in noConflict mode and keeps it on django.jQuery.
 * In the classic admin a global jQuery also exists, because Grappelli
 * puts one there, and several of Cemes's admin widget scripts -
 * keywords_field.js among them - call the global directly.
 *
 * This restores that alias so those scripts keep working. It is slotted
 * into the media list immediately after Django's jquery.init.js (see
 * introspect.filter_media), so it runs before any widget script that
 * depends on it.
 */
(function () {
  "use strict";
  if (window.django && window.django.jQuery) {
    if (!window.jQuery) {
      window.jQuery = window.django.jQuery;
    }
    if (!window.$) {
      window.$ = window.django.jQuery;
    }
  }
})();
