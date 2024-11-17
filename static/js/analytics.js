// Chart configuration and utility functions
const chartColors = {
    new: 'rgb(54, 162, 235)',
    'in-progress': 'rgb(255, 205, 86)',
    completed: 'rgb(75, 192, 192)',
    rejected: 'rgb(255, 99, 132)'
};

function initializeCharts(data) {
    // Add null checks before processing data
    if (!data) {
        console.warn('No analytics data available');
        return;
    }
    
    if (data.daily_referrals) initializeReferralTrends(data);
    if (data.treatment_distribution) initializeTreatmentDistribution(data);
    if (data.status_distribution) initializeStatusDistribution(data);
    if (data.commission_distribution) initializeCommissionDistribution(data);
}

function initializeReferralTrends(data) {
    if (!data.daily_referrals) return;
    const ctx = document.getElementById('referralTrends');
    if (!ctx) return;

    new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            labels: Object.keys(data.daily_referrals),
            datasets: [{
                label: 'Daily Referrals',
                data: Object.values(data.daily_referrals),
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                }
            }
        }
    });
}

function initializeTreatmentDistribution(data) {
    if (!data.treatment_distribution) return;
    const ctx = document.getElementById('treatmentDistribution');
    if (!ctx) return;

    new Chart(ctx.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: Object.keys(data.treatment_distribution),
            datasets: [{
                data: Object.values(data.treatment_distribution),
                backgroundColor: Object.values(chartColors)
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                }
            }
        }
    });
}

function initializeCommissionDistribution(data) {
    if (!data.commission_distribution) return;
    const ctx = document.getElementById('commissionDistribution');
    if (!ctx) return;

    const labels = Object.keys(data.commission_distribution);
    const values = Object.values(data.commission_distribution);

    new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Commission Earnings ($)',
                data: values,
                backgroundColor: 'rgb(75, 192, 192)',
                borderColor: 'rgb(75, 192, 192)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + value;
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$' + context.formattedValue;
                        }
                    }
                }
            }
        }
    });
}

// Date range filter handling
function initializeDateFilter() {
    const startDate = document.getElementById('start-date');
    const endDate = document.getElementById('end-date');
    
    if (startDate && endDate) {
        [startDate, endDate].forEach(input => {
            input.addEventListener('change', () => {
                if (startDate.value && endDate.value) {
                    updateCharts(startDate.value, endDate.value);
                }
            });
        });
    }
}

async function updateCharts(startDate, endDate) {
    try {
        const response = await fetch(`/admin/analytics?start_date=${startDate}&end_date=${endDate}`);
        if (!response.ok) {
            console.warn('Failed to fetch analytics data');
            return;
        }
        const data = await response.json();
        
        // Destroy existing charts
        Chart.instances.forEach(chart => chart.destroy());
        
        // Reinitialize charts with new data
        initializeCharts(data);
    } catch (error) {
        console.error('Error updating charts:', error);
    }
}

// Initialize everything when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    initializeDateFilter();
    
    // Get the analytics data from the page
    const analyticsDataElement = document.getElementById('analytics-data');
    if (analyticsDataElement && analyticsDataElement.textContent) {
        try {
            const analyticsData = JSON.parse(analyticsDataElement.textContent);
            initializeCharts(analyticsData);
        } catch (error) {
            console.warn('Failed to parse analytics data:', error);
        }
    }
});