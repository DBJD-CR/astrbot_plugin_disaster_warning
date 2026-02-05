const { Box, Typography, Paper, Chip, Button, ButtonGroup, Fade, Collapse } = MaterialUI;
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

    const renderEventCard = (evt, isHistory = false) => {
        const isEarthquake = evt.type === 'earthquake' || evt.type === 'earthquake_warning';
        const isTsunami = evt.type === 'tsunami';
        const isWeather = evt.type === 'weather_alarm';

        return (
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                {isEarthquake && (
                    <Chip
                        label={`M${(evt.magnitude || 0).toFixed(1)}`}
                        size={isHistory ? "small" : "medium"}
                        sx={{
                            bgcolor: getMagnitudeColor(evt.magnitude || 0),
                            color: 'white',
                            fontWeight: 600,
                            minWidth: isHistory ? 50 : 60
                        }}
                    />
                )}
                {isTsunami && (
                    <Chip label="🌊" size={isHistory ? "small" : "medium"} color="info" />
                )}
                {isWeather && (
                    <Chip label="☁️" size={isHistory ? "small" : "medium"} color="warning" />
                )}
                {!isEarthquake && !isTsunami && !isWeather && (
                    <Chip label="❓" size={isHistory ? "small" : "medium"} color="default" />
                )}

                <Box sx={{ flex: 1 }}>
                    <Typography variant={isHistory ? "body2" : "body1"} sx={{ fontWeight: 500 }}>
                        {evt.description || '未知位置'}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1.5, mt: 0.5 }}>
                        <Typography variant="caption" color="text.secondary">
                            {formatTimeFriendly(evt.time)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            {evt.source || '未知来源'}
                        </Typography>
                    </Box>
                </Box>
            </Box>
        );
    };

    if (groupedEvents.length === 0) {
        return (
            <Box sx={{ my: 2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h6">📋 最近事件</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 3 }}>
                    暂无事件记录
                </Typography>
            </Box>
        );
    }

    return (
        <Box sx={{ my: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1.5 }}>
                <Typography variant="h6">📋 最近事件</Typography>
                <ButtonGroup size="small">
                    <Button variant={filterType === 'all' ? 'contained' : 'outlined'} onClick={() => setFilterType('all')}>
                        全部
                    </Button>
                    <Button variant={filterType === 'earthquake' ? 'contained' : 'outlined'} onClick={() => setFilterType('earthquake')}>
                        地震
                    </Button>
                    <Button variant={filterType === 'tsunami' ? 'contained' : 'outlined'} onClick={() => setFilterType('tsunami')}>
                        海啸
                    </Button>
                    <Button variant={filterType === 'weather' ? 'contained' : 'outlined'} onClick={() => setFilterType('weather')}>
                        气象
                    </Button>
                </ButtonGroup>
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {groupedEvents.map((group, index) => (
                    <Fade
                        in={true}
                        timeout={300 + index * 50}
                        key={group.id}
                    >
                        <Paper
                            sx={{
                                p: 2,
                                '@keyframes slideUp': {
                                    from: {
                                        opacity: 0,
                                        transform: 'translateY(20px)'
                                    },
                                    to: {
                                        opacity: 1,
                                        transform: 'translateY(0)'
                                    }
                                },
                                animation: `slideUp 0.3s ease-out ${index * 0.05}s both`
                            }}
                        >
                            <Box
                                sx={{
                                    cursor: group.updateCount > 1 ? 'pointer' : 'default',
                                    display: 'flex',
                                    alignItems: 'center'
                                }}
                                onClick={() => group.updateCount > 1 && toggleEventGroup(group.id)}
                            >
                                {renderEventCard(group.latestEvent)}
                                {group.updateCount > 1 && (
                                    <Chip
                                        label={`${group.updateCount} ${expandedEvents.has(group.id) ? '▲' : '▼'}`}
                                        size="small"
                                        color="primary"
                                        variant="outlined"
                                        sx={{ ml: 2 }}
                                    />
                                )}
                            </Box>

                            <Collapse in={expandedEvents.has(group.id)} timeout={300}>
                                {group.updateCount > 1 && (
                                    <Box sx={{ mt: 2, pl: 2, borderLeft: 2, borderColor: 'divider' }}>
                                        {group.events.slice(1).map((evt, idx) => (
                                            <Fade in={expandedEvents.has(group.id)} timeout={200 + idx * 50} key={idx}>
                                                <Box sx={{ py: 1, opacity: 0.7 }}>
                                                    {renderEventCard(evt, true)}
                                                </Box>
                                            </Fade>
                                        ))}
                                    </Box>
                                )}
                            </Collapse>
                        </Paper>
                    </Fade>
                ))}
            </Box>
        </Box>
    );
}
