const { Box } = MaterialUI;

function EventsView() {
    return (
        <Box>
            <div style={{ marginBottom: '24px' }}>
                <HorizontalTimeline />
            </div>
            <div style={{ marginBottom: '24px' }}>
                <WeatherQueryPanel />
            </div>
            <EventsList />
        </Box>
    );
}
