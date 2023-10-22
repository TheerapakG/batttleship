from tgraphics.component import Component
from tgraphics.reactivity import ReadRef, unref


@Component.register("Suspense")
def suspense(
    children: list[Component] | ReadRef[list[Component]],
    fallback: list[Component] | ReadRef[list[Component]],
    **kwargs
):
    return Component.render_xml(
        """
        <Layer>
            <Column>
                <Slot components="children" />
            </Column>
            <Column t-if="not unref(children)">
                <Slot components="fallback" />
            </Column>
        </Layer>
        """,
        **kwargs
    )
