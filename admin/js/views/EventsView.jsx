const { Box } = MaterialUI;

function EventsView() {
    return (
        <Box>
            <div style={{ marginBottom: '24px' }}>
                <HorizontalTimeline />
            </div>
            <EventsList />
        </Box>
    );
}
