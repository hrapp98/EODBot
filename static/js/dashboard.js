document.addEventListener('DOMContentLoaded', function() {
    let chart = null; // Store chart instance
    let currentSort = { column: null, direction: 'asc' };
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize team search functionality
    const teamSearch = document.getElementById('teamSearch');
    if (teamSearch) {
        teamSearch.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            document.querySelectorAll('.user-card').forEach(card => {
                const userName = card.querySelector('.user-name').textContent.toLowerCase();
                const userTitle = card.querySelector('.text-muted')?.textContent.toLowerCase() || '';
                const userEmail = card.querySelector('small')?.textContent.toLowerCase() || '';
                const matches = userName.includes(searchTerm) || 
                              userTitle.includes(searchTerm) || 
                              userEmail.includes(searchTerm);
                card.style.display = matches ? '' : 'none';
            });
        });
    }
    
    // Load team members data
    async function loadTeamMembers() {
        try {
            const teamMembersBody = document.getElementById('teamMembersBody');
            if (!teamMembersBody) return;
            
            // Show loading indicator
            teamMembersBody.innerHTML = `
                <tr id="teamMembersLoading">
                    <td colspan="4" class="text-center">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2">Loading team members...</p>
                    </td>
                </tr>
            `;
            
            // Fetch team members data
            const response = await fetch('/api/team-members');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const users = await response.json();
            
            // Clear loading indicator
            teamMembersBody.innerHTML = '';
            
            // Sort users by name initially
            const sortedUsers = Object.entries(users).sort((a, b) => {
                return a[1].name.localeCompare(b[1].name);
            });
            
            // Add all team members to table
            if (sortedUsers.length > 0) {
                sortedUsers.forEach(([userId, user]) => {
                    const row = document.createElement('tr');
                    row.className = 'user-card';
                    row.dataset.userId = userId;
                    row.dataset.name = user.name;
                    row.dataset.status = user.today_status;
                    row.dataset.missed = user.missed_days || 0;
                    
                    // User cell
                    const userCell = document.createElement('td');
                    userCell.innerHTML = `
                        <div class="d-flex align-items-center">
                            ${user.image ? 
                                `<img src="${user.image}" alt="${user.name}" class="user-avatar me-2" style="width: 20px; height: 20px;">` : 
                                `<div class="user-avatar me-2 d-flex align-items-center justify-content-center bg-primary" style="width: 20px; height: 20px; font-size: 10px;">${user.name.charAt(0)}</div>`
                            }
                            <span class="user-name">${user.name}</span>
                            <span class="d-none">${user.title || ''} ${user.email || ''}</span>
                        </div>
                    `;
                    row.appendChild(userCell);
                    
                    // Status cell
                    const statusCell = document.createElement('td');
                    let statusBadgeClass = 'bg-warning';
                    let statusText = 'Pending';
                    
                    if (user.today_status === 'submitted') {
                        statusBadgeClass = 'bg-success';
                        statusText = 'Submitted';
                    } else if (user.today_status === 'missed') {
                        statusBadgeClass = 'bg-danger';
                        statusText = 'Missed';
                    }
                    
                    statusCell.innerHTML = `<span class="badge ${statusBadgeClass}">${statusText}</span>`;
                    row.appendChild(statusCell);
                    
                    // Missed days cell
                    const missedCell = document.createElement('td');
                    const missed = user.missed_days || 0;
                    let missedBadgeClass = 'bg-success';
                    
                    if (missed > 3) {
                        missedBadgeClass = 'bg-danger';
                    } else if (missed > 0) {
                        missedBadgeClass = 'bg-warning';
                    }
                    
                    missedCell.innerHTML = `<span class="badge ${missedBadgeClass}">${missed}</span>`;
                    row.appendChild(missedCell);
                    
                    // Action cell
                    const actionCell = document.createElement('td');
                    actionCell.innerHTML = `<a href="/dashboard/user/${userId}" class="btn btn-sm btn-outline-primary btn-xs">View</a>`;
                    row.appendChild(actionCell);
                    
                    teamMembersBody.appendChild(row);
                });
            } else {
                teamMembersBody.innerHTML = `
                    <tr>
                        <td colspan="4" class="text-center">No team members found</td>
                    </tr>
                `;
            }
            
            // Add sorting functionality
            document.querySelectorAll('.sortable').forEach(header => {
                header.addEventListener('click', function() {
                    const column = this.dataset.sort;
                    const direction = currentSort.column === column && currentSort.direction === 'asc' ? 'desc' : 'asc';
                    
                    // Update sort indicators
                    document.querySelectorAll('.sortable').forEach(h => {
                        h.classList.remove('sort-asc', 'sort-desc');
                    });
                    this.classList.add(`sort-${direction}`);
                    
                    // Store current sort
                    currentSort.column = column;
                    currentSort.direction = direction;
                    
                    // Sort rows
                    const rows = Array.from(teamMembersBody.querySelectorAll('tr.user-card'));
                    rows.sort((a, b) => {
                        let valueA, valueB;
                        
                        if (column === 'name') {
                            valueA = a.dataset.name;
                            valueB = b.dataset.name;
                        } else if (column === 'status') {
                            valueA = a.dataset.status;
                            valueB = b.dataset.status;
                        } else if (column === 'missed') {
                            valueA = parseInt(a.dataset.missed);
                            valueB = parseInt(b.dataset.missed);
                        }
                        
                        if (typeof valueA === 'number' && typeof valueB === 'number') {
                            return direction === 'asc' ? valueA - valueB : valueB - valueA;
                        } else {
                            return direction === 'asc' ? 
                                String(valueA).localeCompare(String(valueB)) : 
                                String(valueB).localeCompare(String(valueA));
                        }
                    });
                    
                    // Reorder rows
                    rows.forEach(row => teamMembersBody.appendChild(row));
                });
            });
            
        } catch (error) {
            console.error('Error loading team members:', error);
            const teamMembersBody = document.getElementById('teamMembersBody');
            if (teamMembersBody) {
                teamMembersBody.innerHTML = `
                    <tr>
                        <td colspan="4" class="text-center text-danger">
                            <i class="bi bi-exclamation-triangle"></i> Error loading team members
                        </td>
                    </tr>
                `;
            }
        }
    }
    
    // Initialize table sorting
    function initTableSorting() {
        const sortableHeaders = document.querySelectorAll('.sortable');
        if (sortableHeaders.length > 0) {
            sortableHeaders.forEach(header => {
                header.addEventListener('click', function() {
                    const column = this.dataset.sort;
                    let direction = 'asc';
                    
                    // Reset all headers
                    sortableHeaders.forEach(h => {
                        h.classList.remove('sort-asc', 'sort-desc');
                    });
                    
                    // If clicking the same column, toggle direction
                    if (currentSort.column === column) {
                        direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
                    }
                    
                    // Update current sort
                    currentSort = { column, direction };
                    
                    // Update header appearance
                    this.classList.add(`sort-${direction}`);
                    
                    // Sort the table
                    sortTable(column, direction);
                });
            });
        }
    }
    
    // Function to sort table
    function sortTable(column, direction) {
        const teamMembersBody = document.getElementById('teamMembersBody');
        if (!teamMembersBody) return;
        
        const rows = Array.from(teamMembersBody.querySelectorAll('tr.user-card'));
        
        // Sort rows
        rows.sort((a, b) => {
            let aValue, bValue;
            
            if (column === 'name') {
                aValue = a.dataset.name.toLowerCase();
                bValue = b.dataset.name.toLowerCase();
            } else if (column === 'status') {
                aValue = a.dataset.status;
                bValue = b.dataset.status;
            } else if (column === 'missed') {
                aValue = parseInt(a.dataset.missed || 0);
                bValue = parseInt(b.dataset.missed || 0);
            }
            
            // Compare values
            if (column === 'missed') {
                // Numeric comparison for missed days
                return direction === 'asc' ? aValue - bValue : bValue - aValue;
            } else {
                // String comparison for other columns
                if (aValue < bValue) return direction === 'asc' ? -1 : 1;
                if (aValue > bValue) return direction === 'asc' ? 1 : -1;
                return 0;
            }
        });
        
        // Reorder rows in the DOM
        rows.forEach(row => teamMembersBody.appendChild(row));
    }
    
    // Dashboard functionality
    const dateRange = document.getElementById('dateRange');
    if (dateRange) {
        // Function to update dashboard
        async function updateDashboard() {
            try {
                const response = await fetch('/api/dashboard-data');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const dashboardData = await response.json();
                
                // Update stats
                if (document.getElementById('totalUsers')) {
                    document.getElementById('totalUsers').textContent = dashboardData.total_users;
                }
                
                if (document.getElementById('submittedCount')) {
                    document.getElementById('submittedCount').textContent = dashboardData.submitted_count;
                }
                
                if (document.getElementById('submissionRate')) {
                    document.getElementById('submissionRate').textContent = `${dashboardData.submission_rate}%`;
                }
                
                // Update chart if it exists
                if (document.getElementById('submissionChart')) {
                    document.getElementById('submissionChart').dataset.submissions = JSON.stringify(dashboardData.trend_data);
                    
                    // If chart.js is already loaded, update the chart
                    if (typeof Chart !== 'undefined' && document.getElementById('submissionChart').getContext) {
                        const ctx = document.getElementById('submissionChart').getContext('2d');
                        
                        // Destroy existing chart if it exists
                        if (chart) {
                            chart.destroy();
                        }
                        
                        // Create new chart
                        chart = new Chart(ctx, {
                            type: 'line',
                            data: {
                                labels: dashboardData.trend_data.map(d => d.date),
                                datasets: [{
                                    label: 'Submission Rate (%)',
                                    data: dashboardData.trend_data.map(d => d.rate),
                                    borderColor: '#6366f1',
                                    tension: 0.4
                                }]
                            },
                            options: {
                                responsive: true,
                                scales: {
                                    y: {
                                        beginAtZero: true,
                                        max: 100,
                                        title: {
                                            display: true,
                                            text: 'Submission Rate (%)'
                                        }
                                    }
                                },
                                plugins: {
                                    tooltip: {
                                        callbacks: {
                                            label: function(context) {
                                                return `Submission Rate: ${context.raw}%`;
                                            }
                                        }
                                    }
                                }
                            }
                        });
                    }
                }
                
                // Hide loading indicators
                if (document.getElementById('chartLoading')) {
                    document.getElementById('chartLoading').classList.add('d-none');
                }
                
                // Also load team members when dashboard is updated
                loadTeamMembers();
                
            } catch (error) {
                console.error('Error updating dashboard:', error);
                // Show error message
                if (document.getElementById('dashboardError')) {
                    document.getElementById('dashboardError').classList.remove('d-none');
                }
            }
        }
        
        // Update when date range changes
        dateRange.addEventListener('change', function() {
            if (this.value === 'custom') {
                document.getElementById('specificDateContainer').classList.remove('d-none');
            } else {
                document.getElementById('specificDateContainer').classList.add('d-none');
                updateDashboard();
            }
        });
        
        // Update when specific date changes
        const specificDate = document.getElementById('specificDate');
        if (specificDate) {
            specificDate.addEventListener('change', function() {
                if (dateRange.value === 'custom') {
                    updateDashboard();
                }
            });
        }
        
        // Initial update
        updateDashboard();
    } else {
        // If no date range (e.g., on team page), just load team members
        loadTeamMembers();
    }
    
    // Auto-refresh every 5 minutes if on "today" view
    setInterval(() => {
        if (dateRange && dateRange.value === 'today') {
            updateDashboard();
        }
    }, 5 * 60 * 1000);

    // Update recent reports section to handle pagination
    const recentReportsBody = document.getElementById('recentReportsBody');
    let currentPage = 1;
    let hasMoreReports = true;
    let loadingMoreReports = false;
    let reportsPerPage = 20; // Number of reports to load per page

    // Function to load reports
    async function loadReports(page = 1, append = false) {
        if (loadingMoreReports) return; // Prevent multiple simultaneous requests
        
        loadingMoreReports = true;
        
        if (!append) {
            // Show loading indicator for initial load
            recentReportsBody.innerHTML = `
                <tr id="reportsLoading">
                    <td colspan="8" class="text-center">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2">Loading recent reports...</p>
                    </td>
                </tr>
            `;
        } else {
            // Remove existing load more button if present
            const existingLoadMore = document.getElementById('loadMoreButton');
            if (existingLoadMore) {
                existingLoadMore.remove();
            }
            
            // Add loading indicator at the bottom for pagination
            const loadingRow = document.createElement('tr');
            loadingRow.id = 'loadMoreReports';
            loadingRow.innerHTML = `
                <td colspan="8" class="text-center">
                    <div class="spinner-border spinner-border-sm text-primary" role="status">
                        <span class="visually-hidden">Loading more...</span>
                    </div>
                    <span class="ms-2">Loading more reports...</span>
                </td>
            `;
            recentReportsBody.appendChild(loadingRow);
        }

        try {
            // Fetch reports with pagination
            const response = await fetch(`/api/recent-reports?page=${page}&limit=${reportsPerPage}`);
            
            if (!response.ok) {
                throw new Error(`Failed to fetch reports: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Remove loading indicator
            const loadingElement = append ? 
                document.getElementById('loadMoreReports') : 
                document.getElementById('reportsLoading');
            if (loadingElement) {
                loadingElement.remove();
            }

            if (!data.reports || data.reports.length === 0) {
                hasMoreReports = false;
                if (!append) {
                    recentReportsBody.innerHTML = `
                        <tr>
                            <td colspan="8" class="text-center">No reports found</td>
                        </tr>
                    `;
                }
                return;
            }

            // Clear existing content if not appending
            if (!append) {
                recentReportsBody.innerHTML = '';
            }

            // Add reports to the table
            data.reports.forEach(report => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${report.created_at}</td>
                    <td>
                        <div class="d-flex align-items-center">
                            ${report.user_image ? 
                                `<img src="${report.user_image}" class="rounded-circle me-2" width="32" height="32" alt="${report.user_name}">` : 
                                `<div class="rounded-circle bg-secondary text-white d-flex align-items-center justify-content-center me-2" style="width: 32px; height: 32px;">${report.user_name.charAt(0)}</div>`
                            }
                            <a href="/user/${report.user_id}">${report.user_name}</a>
                        </div>
                    </td>
                    <td class="text-cell">${truncateText(report.short_term_projects, 50)}</td>
                    <td class="text-cell">${truncateText(report.long_term_projects, 50)}</td>
                    <td class="text-cell">${truncateText(report.blockers, 50)}</td>
                    <td class="text-cell">${truncateText(report.next_day_goals, 50)}</td>
                    <td class="text-cell">${truncateText(report.tools_used, 50)}</td>
                    <td>
                        <button class="btn btn-sm btn-primary view-report" data-report-id="${report.id}" data-bs-toggle="modal" data-bs-target="#reportDetailModal">
                            <i class="bi bi-eye"></i>
                        </button>
                    </td>
                `;
                recentReportsBody.appendChild(row);
            });

            // Add event listeners to view buttons
            document.querySelectorAll('.view-report').forEach(button => {
                button.addEventListener('click', function() {
                    const reportId = this.getAttribute('data-report-id');
                    viewReportDetails(reportId);
                });
            });

            // Update current page
            currentPage = page;
            
            // Check if we have more reports
            hasMoreReports = data.has_more;
            
            // Add a "Load More" button if there are more reports
            if (hasMoreReports) {
                const loadMoreRow = document.createElement('tr');
                loadMoreRow.id = 'loadMoreButton';
                loadMoreRow.innerHTML = `
                    <td colspan="8" class="text-center py-3">
                        <button class="btn btn-outline-primary" id="loadMoreReportsBtn">
                            <i class="bi bi-arrow-down-circle me-2"></i>Load More Reports
                        </button>
                    </td>
                `;
                recentReportsBody.appendChild(loadMoreRow);
                
                // Add event listener to the load more button
                document.getElementById('loadMoreReportsBtn').addEventListener('click', function() {
                    loadReports(currentPage + 1, true);
                });
            }
            
            // Add event listeners to text cells to show full content in a tooltip or modal
            addTextCellListeners();
            
        } catch (error) {
            console.error('Error loading reports:', error);
            if (!append) {
                recentReportsBody.innerHTML = `
                    <tr>
                        <td colspan="8" class="text-center text-danger">
                            Error loading reports. Please try again.
                        </td>
                    </tr>
                `;
            } else {
                // Remove loading indicator if it exists
                const loadingElement = document.getElementById('loadMoreReports');
                if (loadingElement) {
                    loadingElement.remove();
                }
                
                // Show error message
                const errorRow = document.createElement('tr');
                errorRow.innerHTML = `
                    <td colspan="8" class="text-center text-danger">
                        Error loading more reports. <button class="btn btn-sm btn-outline-danger" id="retryLoadMore">Retry</button>
                    </td>
                `;
                recentReportsBody.appendChild(errorRow);
                
                // Add retry button functionality
                document.getElementById('retryLoadMore')?.addEventListener('click', function() {
                    this.closest('tr').remove();
                    loadReports(currentPage + 1, true);
                });
            }
        } finally {
            loadingMoreReports = false;
        }
    }

    // Helper function to truncate text with "Read more" link
    function truncateText(text, maxLength) {
        if (!text) return '-';
        
        // Clean the text (remove line breaks for display)
        const cleanText = text.replace(/\n/g, ' ').trim();
        
        if (cleanText.length <= maxLength) {
            return cleanText;
        }
        
        return `<span class="truncated-text">${cleanText.substring(0, maxLength)}...</span>`;
    }

    // Initial load
    loadReports();

    // Add scroll event listener to the table container
    const reportsTableContainer = document.querySelector('.reports-table-container');
    reportsTableContainer.addEventListener('scroll', function() {
        if (this.scrollTop > 0) {
            this.classList.add('scrolled');
        } else {
            this.classList.remove('scrolled');
        }
    });

    // Add a function to handle the refresh button
    document.getElementById('refreshReports').addEventListener('click', function() {
        // Reset pagination and reload reports
        currentPage = 1;
        hasMoreReports = true;
        loadReports();
    });

    // Function to view report details
    async function viewReportDetails(reportId) {
        try {
            // Show loading state in modal
            const modalContent = document.getElementById('reportDetailContent');
            modalContent.innerHTML = `
                <div class="text-center py-5">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-3">Loading report details...</p>
                </div>
            `;
            
            // Fetch report details
            const response = await fetch(`/api/report/${reportId}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const report = await response.json();
            
            // Format timestamp
            const timestamp = new Date(report.timestamp);
            const formattedDate = timestamp.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
            });
            const formattedTime = timestamp.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit'
            });
            
            // Update modal content with report details
            modalContent.innerHTML = `
                <div class="d-flex align-items-center mb-4">
                    ${report.user_image ? 
                        `<img src="${report.user_image}" class="rounded-circle me-3" width="48" height="48" alt="${report.user_name}">` : 
                        `<div class="rounded-circle bg-secondary text-white d-flex align-items-center justify-content-center me-3" style="width: 48px; height: 48px; font-size: 1.2rem;">${report.user_name.charAt(0)}</div>`
                    }
                    <div>
                        <h4 class="mb-0">${report.user_name}</h4>
                        <div class="text-muted">
                            <small>${formattedDate} at ${formattedTime}</small>
                        </div>
                    </div>
                </div>
                
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Short-term Projects</h5>
                    <p class="mb-0">${formatReportText(report.short_term_projects)}</p>
                </div>
                
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Long-term Projects</h5>
                    <p class="mb-0">${formatReportText(report.long_term_projects)}</p>
                </div>
                
                ${report.blockers ? `
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Blockers/Challenges</h5>
                    <p class="mb-0">${formatReportText(report.blockers)}</p>
                </div>
                ` : ''}
                
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Next Day Goals</h5>
                    <p class="mb-0">${formatReportText(report.next_day_goals)}</p>
                </div>
                
                ${report.tools_used ? `
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Tools Used</h5>
                    <p class="mb-0">${formatReportText(report.tools_used)}</p>
                </div>
                ` : ''}
                
                ${report.help_needed ? `
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Help Needed</h5>
                    <p class="mb-0">${formatReportText(report.help_needed)}</p>
                </div>
                ` : ''}
                
                ${report.client_feedback ? `
                <div class="report-section mb-4">
                    <h5 class="report-section-title">Client Feedback</h5>
                    <p class="mb-0">${formatReportText(report.client_feedback)}</p>
                </div>
                ` : ''}
                
                <div class="d-flex justify-content-start mt-4">
                    <a href="/user/${report.user_id}" class="btn btn-outline-primary">
                        <i class="bi bi-person"></i> View User Profile
                    </a>
                </div>
            `;
            
        } catch (error) {
            console.error('Error loading report details:', error);
            document.getElementById('reportDetailContent').innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    Error loading report details. Please try again.
                </div>
            `;
        }
    }

    // Helper function to format report text with line breaks
    function formatReportText(text) {
        if (!text) return '-';
        return text.replace(/\n/g, '<br>');
    }

    // Add event listeners to text cells to show full content in a tooltip or modal
    function addTextCellListeners() {
        document.querySelectorAll('.text-cell').forEach(cell => {
            cell.addEventListener('click', function() {
                const text = this.textContent.trim();
                if (text !== '-') {
                    // Find the report ID from the row
                    const reportId = this.closest('tr').querySelector('.view-report').dataset.reportId;
                    // Open the report detail modal
                    document.querySelector(`[data-report-id="${reportId}"]`).click();
                }
            });
        });
    }

    // Call this after loading reports
    function initializeReportsTable() {
        addTextCellListeners();
        
        // Add scroll effect to the reports table
        const reportsTableContainer = document.querySelector('.reports-table-container');
        if (reportsTableContainer) {
            reportsTableContainer.addEventListener('scroll', function() {
                if (this.scrollTop > 0) {
                    this.classList.add('scrolled');
                } else {
                    this.classList.remove('scrolled');
                }
            });
        }
    }
});
