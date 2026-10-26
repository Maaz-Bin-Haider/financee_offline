$(document).ready(function() {
    let autocompleteUrl = $("#search_name").data("autocomplete-url");

    $("#search_name").on("input", function() {
        let query = $(this).val();
        let suggestionsBox = $("#suggestions");

        if(query.length >= 1){
            $.ajax({
                url: autocompleteUrl,
                data: {'term': query},
                dataType: 'json',
                success: function(data){
                    suggestionsBox.empty();
                    if(data.length > 0){
                        data.forEach(function(party){
                            $("<div>")
                                .text(party)
                                .css({padding: "5px", cursor: "pointer", borderBottom: "1px solid #ddd"})
                                .appendTo(suggestionsBox)
                                .on("click", function(){
                                    $("#search_name").val(party);
                                    suggestionsBox.hide();
                                });
                        });
                        suggestionsBox.show();
                    } else {
                        suggestionsBox.hide();
                    }
                }
            });
        } else {
            suggestionsBox.hide();
        }
    });

    $(document).on("click", function(e){
        if(!$(e.target).closest("#search_name, #suggestions").length){
            $("#suggestions").hide();
        }
    });
});
