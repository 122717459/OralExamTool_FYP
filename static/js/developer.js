document.addEventListener("DOMContentLoaded", async () => {
  loadLogs();
});

async function loadLogs() {
  const tbody = document.getElementById("logsTableBody");

  const resp = await fetch("/api/logs?per_page=50");
  const data = await resp.json();

  tbody.innerHTML = "";

  for (const item of data.items) {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${item.id}</td>
      <td>${item.user_id}</td>
      <td>${item.model_name}</td>
      <td>${item.created_at}</td>
      <td>
        <button onclick="deleteLog(${item.id})">Delete</button>
      </td>
    `;

    tbody.appendChild(row);
  }
}

async function deleteLog(id) {
  if (!confirm("Delete this log?")) return;

  await fetch(`/api/logs/${id}`, { method: "DELETE" });

  loadLogs();
}
//  CHARTS

document.addEventListener("DOMContentLoaded", () => {

    // This is from Chatgpt
  // Language Pie Chart
  const langLabels = examLanguageData.map(item => item[0]);
  const langCounts = examLanguageData.map(item => item[1]);

// Draw a pie chart showing how many exams were in each language
  new Chart(document.getElementById("languageChart"), {
    type: "pie",
    data: {
      labels: langLabels,
      datasets: [{
        data: langCounts
      }]
    }
  });

    // This is from Chatgpt
  // Difficulty Bar Chart
  const diffLabels = examDifficultyData.map(item => item[0]);
  const diffCounts = examDifficultyData.map(item => item[1]);

// Draws a bar chart showing how many exams were in each difficulty
  new Chart(document.getElementById("difficultyChart"), {
    type: "bar",
    data: {
      labels: diffLabels,
      datasets: [{
        label: "Number of Exams",
        data: diffCounts
      }]
    },
    options: {
      scales: {
        y: {
          beginAtZero: true
        }
      }
    }
  });

});

// This is the chatgpt prompt used to make the charts
//Write JavaScript code for a web dashboard that creates two charts using the **Chart.js** library.
//The page will receive two datasets from the backend:
//1. examLanguageData – an array containing language names and counts
 //  Example: `[["english", 20], ["french", 10], ["german", 5]]`
//2. examDifficultyData – an array containing difficulty levels and counts
  // Example: `[["beginner", 12], ["moderate", 18], ["expert", 5]]`
//The script should:
//1. Run when the page loads using **DOMContentLoaded**.
//2. Create a pie chart showing the distribution of exam languages.
//3. Create a bar chart showing the number of exams by difficulty level.
//4. Extract labels and values from the arrays.
//5. Display the charts in two `<canvas>` elements with the IDs:
 //   `languageChart`
  //  `difficultyChart`
//The bar chart should start its Y-axis at zero so the comparison between difficulty levels is clear.
