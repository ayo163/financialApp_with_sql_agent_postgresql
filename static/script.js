const form = document.getElementById("questionForm");
const questionInput = document.getElementById("question");
const submitBtn = document.getElementById("submitBtn");
const loading = document.getElementById("loading");
const resultContainer = document.getElementById("resultContainer");
const answerBox = document.getElementById("answer");


form.addEventListener("submit", async function(event) {
    event.preventDefault();

    const question = questionInput.value.trim();

    if (!question) {
        return;
    }

    submitBtn.disabled = true;
    loading.classList.remove("d-none");
    resultContainer.classList.add("d-none");

    try {
        const response = await fetch("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                question: question
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Request failed");
        }

        // Display AI response as sanitized HTML
        answerBox.innerHTML = data.answer;

        // Apply Bootstrap styling to generated tables
        answerBox.querySelectorAll("table").forEach(table => {
            table.classList.add(
                "table",
                "table-bordered",
                "table-striped",
                "table-hover"
            );

            // Make table responsive
            const wrapper = document.createElement("div");
            wrapper.className = "table-responsive";

            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });

        // Display result container
        resultContainer.classList.remove("d-none");

        // ====================================
        // DISPLAY PLOTLY CHART IF AVAILABLE
        // ====================================

        if (data.chart) {

            // Create chart container
            const chartDiv = document.createElement("div");

            chartDiv.className = "mt-4";
            chartDiv.style.width = "100%";
            chartDiv.style.minHeight = "400px";

            // Add chart below AI response
            answerBox.appendChild(chartDiv);

            // Render Plotly graph
            await Plotly.newPlot(
                chartDiv,
                data.chart.data,
                data.chart.layout,
                {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false
                }
            );
        }

    } catch (error) {

        answerBox.textContent = "Error: " + error.message;
        resultContainer.classList.remove("d-none");

    } finally {

        submitBtn.disabled = false;
        loading.classList.add("d-none");

    }
});
