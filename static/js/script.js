function fetchSuggestions() {
    const term = document.getElementById("search").value;
    if (!term) {
        document.getElementById("suggestions").innerHTML = "";
        return;
    }
    fetch("/autocomplete?term=" + encodeURIComponent(term))
        .then(response => response.json())
        .then(data => {
            const suggestions = data.suggestions || [];
            const suggestionsHtml = suggestions.map(suggestion => 
                `<li onclick="selectSuggestion('${suggestion.name}')">
                    ${suggestion.name} (검색횟수: ${suggestion.select_count} 회)
                 </li>`
            ).join('');
            document.getElementById("suggestions").innerHTML = suggestionsHtml;
        });
}

function selectSuggestion(suggestion) {
    document.getElementById("search").value = suggestion;
    document.getElementById("suggestions").innerHTML = "";
}

function clearSearch() {
    const term = document.getElementById("search").value;
    
    // 기존 기능 유지
    document.getElementById("search").value = "";
    document.getElementById("suggestions").innerHTML = "";

    // select_count 증가 요청
    if (term) {
        fetch('/increment_count', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ term: term })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error:', data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
    }
}
