// /* ============================================================
//    party_forms.js  —  Unified JS for Add Party & Update Party
//    Deps: jQuery 3.6+, SweetAlert2 11+
//    ============================================================ */

// $(function () {

//   /* ──────────────────────────────────────────────
//      1.  AUTOCOMPLETE  (Update Party page)
//   ────────────────────────────────────────────── */
//   const $searchInput   = $("#search_name");
//   const $suggestionsBox = $("#suggestions");

//   if ($searchInput.length) {
//     const autocompleteUrl = $searchInput.data("autocomplete-url");

//     $searchInput.on("input", function () {
//       const query = $(this).val().trim();

//       if (query.length < 1) {
//         $suggestionsBox.hide().empty();
//         return;
//       }

//       $.ajax({
//         url: autocompleteUrl,
//         data: { term: query },
//         dataType: "json",
//         success: function (data) {
//           $suggestionsBox.empty();
//           if (data.length) {
//             data.forEach(function (party) {
//               $("<div>")
//                 .text(party)
//                 .appendTo($suggestionsBox)
//                 .on("click", function () {
//                   $searchInput.val(party);
//                   $suggestionsBox.hide().empty();
//                 });
//             });
//             $suggestionsBox.show();
//           } else {
//             $suggestionsBox.hide();
//           }
//         },
//       });
//     });

//     /* Close on outside click */
//     $(document).on("click", function (e) {
//       if (!$(e.target).closest("#search_name, #suggestions").length) {
//         $suggestionsBox.hide();
//       }
//     });

//     /* Keyboard nav for suggestions */
//     $searchInput.on("keydown", function (e) {
//       const $items = $suggestionsBox.find("div");
//       const $active = $suggestionsBox.find("div.active");
//       if (!$suggestionsBox.is(":visible") || !$items.length) return;

//       if (e.key === "ArrowDown") {
//         e.preventDefault();
//         const $next = $active.length
//           ? $active.removeClass("active").next()
//           : $items.first();
//         $next.addClass("active");
//         $searchInput.val($next.text());
//       } else if (e.key === "ArrowUp") {
//         e.preventDefault();
//         const $prev = $active.length
//           ? $active.removeClass("active").prev()
//           : $items.last();
//         $prev.addClass("active");
//         $searchInput.val($prev.text());
//       } else if (e.key === "Enter") {
//         if ($active.length) {
//           e.preventDefault();
//           $active.trigger("click");
//         }
//       } else if (e.key === "Escape") {
//         $suggestionsBox.hide();
//       }
//     });
//   }


//   /* ──────────────────────────────────────────────
//      2.  ADD NEW PARTY — AJAX form submit
//   ────────────────────────────────────────────── */
//   const $createForm = $("#create_party_form");

//   if ($createForm.length) {
//     $createForm.on("submit", function (e) {
//       e.preventDefault();

//       const $btn      = $createForm.find(".btn-submit");
//       const $btnText  = $btn.find(".btn-text");
//       const origText  = $btnText.text();

//       // Loading state
//       $btn.addClass("loading");
//       $btnText.text("Saving…");

//       const formData = new FormData(this);

//       fetch("", {
//         method: "POST",
//         body: formData,
//         headers: {
//           "X-CSRFToken": $createForm.find("[name=csrfmiddlewaretoken]").val(),
//         },
//       })
//         .then((r) => r.json())
//         .then((data) => {
//           $btn.removeClass("loading");
//           $btnText.text(origText);

//           if (data.status === "success") {
//             Swal.fire({
//               icon: "success",
//               title: "Party Created",
//               text: data.message,
//               showConfirmButton: false,
//               timer: 2500,
//               timerProgressBar: true,
//               customClass: { popup: "swal-party" },
//             }).then(() => location.reload());
//           } else {
//             Swal.fire({
//               icon: "error",
//               title: "Could Not Save",
//               text: data.message,
//               confirmButtonText: "Got it",
//               customClass: { popup: "swal-party" },
//             });
//           }
//         })
//         .catch(() => {
//           $btn.removeClass("loading");
//           $btnText.text(origText);
//           Swal.fire({
//             icon: "error",
//             title: "Network Error",
//             text: "Something went wrong. Please try again.",
//             confirmButtonText: "OK",
//             customClass: { popup: "swal-party" },
//           });
//         });
//     });
//   }


//   /* ──────────────────────────────────────────────
//      3.  UPDATE PARTY — Django messages toasts
//          (shown via page reload; rendered server-side)
//   ────────────────────────────────────────────── */
//   // Django messages are injected via the template tag; 
//   // we expose a helper so the template can trigger them.
//   window.showDjangoMessage = function (level, text) {
//     const icon = level === "success" ? "success" : "error";
//     const title = level === "success" ? "Updated Successfully" : "Error";
//     Swal.fire({
//       icon,
//       title,
//       text,
//       showConfirmButton: level !== "success",
//       timer: level === "success" ? 2500 : undefined,
//       timerProgressBar: level === "success",
//       confirmButtonText: "OK",
//       customClass: { popup: "swal-party" },
//     });
//   };


//   /* ──────────────────────────────────────────────
//      4.  INPUT POLISH — number field guard
//   ────────────────────────────────────────────── */
//   $("#opening_balance").on("input", function () {
//     if ($(this).val() < 0) $(this).val(0);
//   });


//   /* ──────────────────────────────────────────────
//      5.  Autocomplete active-item highlight style
//   ────────────────────────────────────────────── */
//   $(document).on("mouseenter", "#suggestions div", function () {
//     $("#suggestions div").removeClass("active");
//     $(this).addClass("active");
//   });
// });


/* ============================================================
   party_forms.js  —  Unified JS for Add Party & Update Party
   Deps: jQuery 3.6+, SweetAlert2 11+
   ============================================================ */

$(function () {

  /* ──────────────────────────────────────────────
     1.  AUTOCOMPLETE  (Update Party page)
  ────────────────────────────────────────────── */
  const $searchInput   = $("#search_name");
  const $suggestionsBox = $("#suggestions");

  if ($searchInput.length) {
    const autocompleteUrl = $searchInput.data("autocomplete-url");

    $searchInput.on("input", function () {
      const query = $(this).val().trim();

      if (query.length < 1) {
        $suggestionsBox.hide().empty();
        return;
      }

      $.ajax({
        url: autocompleteUrl,
        data: { term: query },
        dataType: "json",
        success: function (data) {
          $suggestionsBox.empty();
          if (data.length) {
            data.forEach(function (party) {
              $("<div>")
                .text(party)
                .appendTo($suggestionsBox)
                .on("click", function () {
                  $searchInput.val(party);
                  $suggestionsBox.hide().empty();
                  // Submit the search form immediately so party data loads
                  // without the user having to manually click the Search button.
                  $searchInput.closest("form").submit();
                });
            });
            $suggestionsBox.show();
          } else {
            $suggestionsBox.hide();
          }
        },
      });
    });

    /* Close on outside click */
    $(document).on("click", function (e) {
      if (!$(e.target).closest("#search_name, #suggestions").length) {
        $suggestionsBox.hide();
      }
    });

    /* Keyboard nav for suggestions */
    $searchInput.on("keydown", function (e) {
      const $items = $suggestionsBox.find("div");
      const $active = $suggestionsBox.find("div.active");
      if (!$suggestionsBox.is(":visible") || !$items.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const $next = $active.length
          ? $active.removeClass("active").next()
          : $items.first();
        $next.addClass("active");
        $searchInput.val($next.text());
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const $prev = $active.length
          ? $active.removeClass("active").prev()
          : $items.last();
        $prev.addClass("active");
        $searchInput.val($prev.text());
      } else if (e.key === "Enter") {
        const $allItems = $suggestionsBox.find("div");
        if ($active.length) {
          e.preventDefault();
          $active.trigger("click");  // click handler now also submits the form
        } else if ($allItems.length === 1) {
          // Only one suggestion — auto-select and submit
          e.preventDefault();
          $allItems.first().trigger("click");
        }
        // If multiple items and none highlighted: let form submit naturally
        // with the typed text (server will do the lookup)
      } else if (e.key === "Escape") {
        $suggestionsBox.hide();
      }
    });
  }


  /* ──────────────────────────────────────────────
     2.  ADD NEW PARTY — AJAX form submit
  ────────────────────────────────────────────── */
  const $createForm = $("#create_party_form");

  if ($createForm.length) {
    $createForm.on("submit", function (e) {
      e.preventDefault();

      const $btn      = $createForm.find(".btn-submit");
      const $btnText  = $btn.find(".btn-text");
      const origText  = $btnText.text();

      // Loading state
      $btn.addClass("loading");
      $btnText.text("Saving…");

      const formData = new FormData(this);

      fetch("", {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": $createForm.find("[name=csrfmiddlewaretoken]").val(),
        },
      })
        .then((r) => r.json())
        .then((data) => {
          $btn.removeClass("loading");
          $btnText.text(origText);

          if (data.status === "success") {
            // Swal.fire({
            //   icon: "success",
            //   title: "Party Created",
            //   text: data.message,
            //   showConfirmButton: false,
            //   timer: 2500,
            //   timerProgressBar: true,
            //   customClass: { popup: "swal-party" },
            // }).then(() => location.reload());
            Alerts.success(data.message, { title: "Party Created" }).then(() => location.reload());
          } else {
            // Swal.fire({
            //   icon: "error",
            //   title: "Could Not Save",
            //   text: data.message,
            //   confirmButtonText: "Got it",
            //   customClass: { popup: "swal-party" },
            // });
            Alerts.error(data.message, { title: "Could Not Save" });
          }
        })
        .catch(() => {
          $btn.removeClass("loading");
          $btnText.text(origText);
          // Swal.fire({
          //   icon: "error",
          //   title: "Network Error",
          //   text: "Something went wrong. Please try again.",
          //   confirmButtonText: "OK",
          //   customClass: { popup: "swal-party" },
          // });
          Alerts.error("Something went wrong. Please try again.", { title: "Network Error" });
        });
    });
  }


  /* ──────────────────────────────────────────────
     3.  UPDATE PARTY — Django messages toasts
         (shown via page reload; rendered server-side)
  ────────────────────────────────────────────── */
  // Django messages are injected via the template tag; 
  // we expose a helper so the template can trigger them.
  window.showDjangoMessage = function (level, text) {
    // const icon = level === "success" ? "success" : "error";
    // const title = level === "success" ? "Updated Successfully" : "Error";
    // Swal.fire({
    //   icon,
    //   title,
    //   text,
    //   showConfirmButton: level !== "success",
    //   timer: level === "success" ? 2500 : undefined,
    //   timerProgressBar: level === "success",
    //   confirmButtonText: "OK",
    //   customClass: { popup: "swal-party" },
    // });
    if (level === "success") {
      Alerts.success(text, { title: "Updated Successfully" });
    } else {
      Alerts.error(text);
    }
  };


  /* ──────────────────────────────────────────────
     4.  INPUT POLISH — number field guard
  ────────────────────────────────────────────── */
  $("#opening_balance").on("input", function () {
    if ($(this).val() < 0) $(this).val(0);
  });


  /* ──────────────────────────────────────────────
     5.  Autocomplete active-item highlight style
  ────────────────────────────────────────────── */
  $(document).on("mouseenter", "#suggestions div", function () {
    $("#suggestions div").removeClass("active");
    $(this).addClass("active");
  });
});