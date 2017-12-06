import datetime
from time import sleep, time
from unittest.case import TestCase
from uuid import uuid4

from eventsourcing.domain.model.entity import VersionedEntity, TimestampedEntity
from eventsourcing.domain.model.events import DomainEvent
from eventsourcing.exceptions import DataIntegrityError
from eventsourcing.utils.topic import get_topic
from eventsourcing.infrastructure.sequenceditem import SequencedItem
from eventsourcing.infrastructure.sequenceditemmapper import SequencedItemMapper


class Event1(VersionedEntity.Event):
    pass


class Event2(TimestampedEntity.Event):
    pass


class Event3(DomainEvent):
    pass


class ValueObject1(object):
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return self.__dict__ != other.__dict__


class TestSequencedItemMapper(TestCase):
    def test_with_versioned_entity_event(self):
        # Setup the mapper, and create an event.
        mapper = SequencedItemMapper(
            sequenced_item_class=SequencedItem,
            sequence_id_attr_name='originator_id',
            position_attr_name='originator_version'
        )
        entity_id1 = uuid4()
        event1 = Event1(originator_id=entity_id1, originator_version=101, __previous_hash__='')

        # Check to_sequenced_item() method results in a sequenced item.
        sequenced_item = mapper.to_sequenced_item(event1)
        self.assertIsInstance(sequenced_item, SequencedItem)
        self.assertEqual(sequenced_item.position, 101)
        self.assertEqual(sequenced_item.sequence_id, entity_id1)
        self.assertEqual(sequenced_item.topic, get_topic(Event1))
        self.assertTrue(sequenced_item.data)

        # Use the returned values to create a new sequenced item.
        sequenced_item_copy = SequencedItem(
            sequence_id=sequenced_item.sequence_id,
            position=sequenced_item.position,
            topic=sequenced_item.topic,
            data=sequenced_item.data,
            hash=sequenced_item.hash,
        )

        # Check from_sequenced_item() returns an event.
        domain_event = mapper.from_sequenced_item(sequenced_item_copy)
        self.assertIsInstance(domain_event, Event1)
        self.assertEqual(domain_event.originator_id, event1.originator_id)
        self.assertEqual(domain_event.originator_version, event1.originator_version)

    def test_with_timestamped_entity_event(self):
        # Setup the mapper, and create an event.
        mapper = SequencedItemMapper(
            sequenced_item_class=SequencedItem,
            sequence_id_attr_name='originator_id',
            position_attr_name='timestamp'
        )
        before = time()
        sleep(0.000001)  # Avoid test failing due to timestamp having limited precision.
        event2 = Event2(originator_id='entity2', __previous_hash__='')
        sleep(0.000001)  # Avoid test failing due to timestamp having limited precision.
        after = time()

        # Check to_sequenced_item() method results in a sequenced item.
        sequenced_item = mapper.to_sequenced_item(event2)
        self.assertIsInstance(sequenced_item, SequencedItem)
        self.assertGreater(sequenced_item.position, before)
        self.assertLess(sequenced_item.position, after)
        self.assertEqual(sequenced_item.sequence_id, 'entity2')
        self.assertEqual(sequenced_item.topic, get_topic(Event2))
        self.assertTrue(sequenced_item.data)

        # Use the returned values to create a new sequenced item.
        sequenced_item_copy = SequencedItem(
            sequence_id=sequenced_item.sequence_id,
            position=sequenced_item.position,
            topic=sequenced_item.topic,
            data=sequenced_item.data,
            hash=sequenced_item.hash,
        )

        # Check from_sequenced_item() returns an event.
        domain_event = mapper.from_sequenced_item(sequenced_item_copy)
        self.assertIsInstance(domain_event, Event2)
        self.assertEqual(domain_event.originator_id, event2.originator_id)
        self.assertEqual(domain_event.timestamp, event2.timestamp)

    def test_with_different_types_of_event_attributes(self):
        # Setup the mapper, and create an event.
        mapper = SequencedItemMapper(
            sequenced_item_class=SequencedItem,
            sequence_id_attr_name='originator_id',
            position_attr_name='a'
        )

        # Check value objects can be compared ok.
        self.assertEqual(ValueObject1('value1'), ValueObject1('value1'))
        self.assertNotEqual(ValueObject1('value1'), ValueObject1('value2'))

        # Create an event with dates and datetimes.
        event3 = Event3(
            originator_id='entity3',
            originator_version=303,
            a=datetime.datetime(2017, 3, 22, 9, 12, 14),
            b=datetime.date(2017, 3, 22),
            c=uuid4(),
            # d=Decimal(1.1),
            e=ValueObject1('value1'),
        )

        # Check to_sequenced_item() method results in a sequenced item.
        sequenced_item = mapper.to_sequenced_item(event3)

        # Use the returned values to create a new sequenced item.
        sequenced_item_copy = SequencedItem(
            sequence_id=sequenced_item.sequence_id,
            position=sequenced_item.position,
            topic=sequenced_item.topic,
            data=sequenced_item.data,
            hash=sequenced_item.hash,
        )

        # Check from_sequenced_item() returns an event.
        domain_event = mapper.from_sequenced_item(sequenced_item_copy)
        self.assertIsInstance(domain_event, Event3)
        self.assertEqual(domain_event.originator_id, event3.originator_id)
        self.assertEqual(domain_event.a, event3.a)
        self.assertEqual(domain_event.b, event3.b)
        self.assertEqual(domain_event.c, event3.c)
        # self.assertEqual(domain_event.d, event3.d)
        self.assertEqual(domain_event.e, event3.e)

    def test_with_data_integrity(self):
        mapper = SequencedItemMapper(
            sequenced_item_class=SequencedItem,
            with_data_integrity=True,
        )

        # Create an event with a value.
        orig_event = DomainEvent(
            sequence_id='1',
            position=0,
            a=555,
        )

        # Check the sequenced item has expected hash.
        hash = '67e5d9c563c59ee7c078bac03053bcd7db207944b91dde2e956382bac309a35c'
        sequenced_item = mapper.to_sequenced_item(orig_event)
        self.assertEqual('{"a":555}', sequenced_item.data)
        self.assertEqual(hash, sequenced_item.hash)

        # Check the sequenced item with a hash prefix maps to a domain event.
        mapped_event = mapper.from_sequenced_item(sequenced_item)
        self.assertEqual(mapped_event.a, 555)

        # Check a damaged item causes an exception.
        damaged_item = SequencedItem(
            sequence_id=sequenced_item.sequence_id,
            position=sequenced_item.position,
            topic=sequenced_item.topic,
            data='{"a":554}',
            hash='',
        )

        with self.assertRaises(DataIntegrityError):
            mapper.from_sequenced_item(damaged_item)

        # Check a damaged item causes an exception.
        damaged_item = SequencedItem(
            sequence_id=sequenced_item.sequence_id,
            position=sequenced_item.position,
            topic='mypackage.' + sequenced_item.topic,
            data=sequenced_item.data,
            hash=sequenced_item.hash,
        )

        with self.assertRaises(DataIntegrityError):
            mapper.from_sequenced_item(damaged_item)

