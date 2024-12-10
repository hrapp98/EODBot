document.addEventListener('DOMContentLoaded', function() {
    // Submission chart
    const ctx = document.getElementById('submissionChart').getContext('2d');
    
    // Sample data - in production this would come from the backend
    const submissionData = {
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
        datasets: [{
            label: 'Submissions',
            data: [12, 15, 13, 14, 11],
            backgroundColor: 'rgba(75, 192, 192, 0.2)',
            borderColor: 'rgba(75, 192, 192, 1)',
            borderWidth: 1
        }]
    };
    
    new Chart(ctx, {
        type: 'bar',
        data: submissionData,
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Number of Submissions'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
    
    // Auto-refresh every 5 minutes
    setInterval(() => {
        window.location.reload();
    }, 5 * 60 * 1000);
});
