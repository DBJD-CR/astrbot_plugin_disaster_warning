const { Box, Typography, Collapse } = MaterialUI;
const { useState, useMemo } = React;

function EventsList() {
    const { state } = useAppContext();
    const { events } = state;
    const [filterType, setFilterType] = useState('all');
    const [expandedEvents, setExpandedEvents] = useState(new Set());

    const filteredEvents = useMemo(() => {
        if (filterType === 'all') return events;
        return events.filter(evt => {
            const type = evt.type || '';
            if (filterType === 'earthquake') {
                return type === 'earthquake' || type === 'earthquake_warning';
            }
            if (filterType === 'tsunami') {
                return type === 'tsunami';
            }
            if (filterType === 'weather') {
                return type === 'weather_alarm';
            }
            return true;
        });
    }, [events, filterType]);

    const groupedEvents = useMemo(() => {
        const groups = {};

        for (const evt of filteredEvents) {
            const eventId = evt.event_id || evt.id || `${evt.time}-${evt.description}`;
            if (!groups[eventId]) {
                groups[eventId] = {
                    id: eventId,
                    events: [],
                    latestEvent: null
                };
            }
            groups[eventId].events.push(evt);
        }

        for (const id in groups) {
            groups[id].events.sort((a, b) => new Date(b.time) - new Date(a.time));
            groups[id].latestEvent = groups[id].events[0];
            groups[id].updateCount = groups[id].events.length;
        }

        return Object.values(groups).sort((a, b) =>
            new Date(b.latestEvent.time) - new Date(a.latestEvent.time)
        );
    }, [filteredEvents]);

    const toggleEventGroup = (groupId) => {
        setExpandedEvents(prev => {
            const newSet = new Set(prev);
            if (newSet.has(groupId)) {
                newSet.delete(groupId);
            } else {
                newSet.add(groupId);
            }
            return newSet;
        });
    };

    const renderEventCard = (evt, isHistory = false, isExpandable = false, isExpanded = false) => {
        const isEarthquake = evt.type === 'earthquake' || evt.type === 'earthquake_warning';
        const isTsunami = evt.type === 'tsunami';
        const isWeather = evt.type === 'weather_alarm';

        let badgeContent = '❓';
        let badgeClass = 'badge-unknown';

        if (isEarthquake) {
            badgeContent = (evt.magnitude || 0).toFixed(1);
            badgeClass = 'badge-earthquake';
        } else if (isTsunami) {
            badgeContent = '🌊';
            badgeClass = 'badge-tsunami';
        } else if (isWeather) {
            badgeContent = '☁️';
            badgeClass = 'badge-weather';
        }

        return (
            <div className={`event-card ${isExpandable ? 'clickable' : ''}`} style={{ 
                marginBottom: isHistory ? '4px' : '0',
                padding: isHistory ? '12px 20px' : ''
            }}>
                <div className={`mag-badge ${badgeClass}`} style={{ 
                    width: isHistory ? '40px' : '56px',
                    height: isHistory ? '40px' : '56px',
                    fontSize: isHistory ? '14px' : '18px'
                }}>
                    {badgeContent}
                </div>

                <div className="event-main">
                    <Typography variant={isHistory ? "body2" : "h6"} sx={{ fontWeight: 700, color: 'text.primary', mb: 0.5 }}>
                        {evt.description || '未知位置'}
                    </Typography>
                    <div className="event-meta" style={{ opacity: 0.6 }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            🕒 {formatTimeFriendly(evt.time)}
                        </span>
                        <span style={{ margin: '0 8px' }}>•</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            📡 {evt.source || '未知来源'}
                        </span>
                    </div>
                </div>

                {isExpandable && (
                    <div className="update-badge">
                        <span className="update-count">{isExpanded ? 'Collapse' : `${evt.updateCount || ''} Updates`}</span>
                        <span className="update-icon">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                )}
            </div>
        );
    };

    if (groupedEvents.length === 0) {
        return (
            <div className="card" style={{ textAlign: 'center', padding: '80px' }}>
                <Typography variant="h2" sx={{ opacity: 0.1, mb: 2 }}>📭</Typography>
                <Typography variant="body1" sx={{ opacity: 0.5 }}>暂无最近的事件记录</Typography>
            </div>
        );
    }

    return (
        <Box sx={{ my: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4, flexWrap: 'wrap', gap: 2 }}>
                <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.5px', color: 'text.primary' }}>
                    最近事件记录
                </Typography>
                
                <div className="filter-group">
                    {[
                        { id: 'all', label: 'All' },
                        { id: 'earthquake', label: 'Earthquake' },
                        { id: 'tsunami', label: 'Tsunami' },
                        { id: 'weather', label: 'Weather' }
                    ].map(item => (
                        <button 
                            key={item.id}
                            className={`btn-filter ${filterType === item.id ? 'active' : ''}`}
                            onClick={() => setFilterType(item.id)}
                        >
                            {filterType === item.id && <span style={{ fontSize: '12px' }}>✓</span>}
                            {item.label}
                        </button>
                    ))}
                </div>
            </Box>

            <div className="events-list">
                {groupedEvents.map((group) => (
                    <div key={group.id} className="event-group">
                        <div onClick={() => group.updateCount > 1 && toggleEventGroup(group.id)}>
                            {renderEventCard(
                                { ...group.latestEvent, updateCount: group.updateCount }, 
                                false, 
                                group.updateCount > 1,
                                expandedEvents.has(group.id)
                            )}
                        </div>

                        <Collapse in={expandedEvents.has(group.id)} timeout={300}>
                            {group.updateCount > 1 && (
                                <div style={{ 
                                    padding: '12px 0 12px 64px',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '12px',
                                    marginTop: '8px'
                                }}>
                                    {group.events.slice(1).map((evt, idx) => (
                                        <div key={idx}>
                                            {renderEventCard(evt, true)}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </Collapse>
                    </div>
                ))}
            </div>
        </Box>
    );
}
